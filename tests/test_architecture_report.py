"""Architecture notices are evidence-backed and never add a review gate."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main
import architecture_report as report


SHA = "a" * 40
HEAD = "b" * 40
PR = "https://github.com/org/repo/pull/5"
DECISION = {"kind": "decision", "planned": False, "title": "Separate production RDS",
            "impact": "Adds a new database instance and deployment cost",
            "paths": ["deploy/database.tf"]}


class ArchitecturalAnalysis(unittest.TestCase):
    def test_collect_reads_archived_design_and_committed_diff_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            archived = repo / "openspec/changes/archive/2026-09-29-example"
            (archived / "specs/db").mkdir(parents=True)
            (archived / "proposal.md").write_text("Use separate data")
            (archived / "design.md").write_text("Existing DB instance")
            (archived / "specs/db/spec.md").write_text("### Requirement: Storage")
            with patch.object(report, "_git", side_effect=[HEAD + "\n",
                                                         "deploy/database.tf\n", "new RDS diff"]):
                data = report.collect(repo, SHA, "openspec/changes/archive/2026-09-29-example")
        self.assertEqual(data["paths"], ["deploy/database.tf"])
        self.assertIn("Existing DB instance", data["planned"])
        self.assertEqual(data["head"], HEAD)
        self.assertTrue(data["complete"])

    def test_invalid_or_unsupported_claims_are_filtered(self):
        raw = [DECISION, dict(DECISION, paths=["secrets/.env"]),
               dict(DECISION, planned="false"), dict(DECISION, impact="")]
        found = report.parse(json.dumps({"decisions": raw}), ["deploy/database.tf"])
        self.assertEqual(found, [DECISION])
        with self.assertRaisesRegex(ValueError, "changed-file evidence"):
            report.parse(json.dumps({"decisions": [dict(DECISION, paths=["secrets/.env"])]}),
                         ["deploy/database.tf"])
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            report.parse("not json", ["deploy/database.tf"])
        self.assertIn("not specified", report.format_report(PR, HEAD, found))
        self.assertIn("blob/" + HEAD + "/deploy/database.tf", report.format_report(PR, HEAD, found))
        self.assertEqual(report.changed(found, found), [])
        self.assertEqual(report.changed(found, [dict(DECISION, impact="New deployment boundary")]),
                         [dict(DECISION, impact="New deployment boundary")])
        removed = report.changed(found, [])
        self.assertEqual(removed[0]["kind"], "removed")
        self.assertIn("Removed decision", report.format_report(PR, HEAD, removed, update=True))

    def test_truncated_diff_never_claims_complete_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            archived = repo / "openspec/changes/archive/2026-09-29-example"
            archived.mkdir(parents=True)
            (archived / "design.md").write_text("## Design\nPlan")
            with patch.object(report, "_git", side_effect=[HEAD, "deploy/database.tf\n",
                                                         "X" * (report.DIFF_MAX + 10)]):
                result = report.collect(repo, SHA, "openspec/changes/archive/2026-09-29-example")
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["diff"]), report.DIFF_MAX)
        self.assertNotIn("No additional significant", report.format_report(PR, HEAD, [],
                                                                            complete=False))

    def test_validation_error_identifies_schema_and_path_failures(self):
        for changes, reason in (({"kind": "decision|assumption"}, "kind must"),
                                ({"planned": "false"}, "JSON boolean"),
                                ({"title": "tiny"}, "5-120"),
                                ({"impact": "x" * 301}, "5-300"),
                                ({"paths": ["deploy/database.tf:12"]}, "exact changed-file")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                report.parse(json.dumps({"decisions": [dict(DECISION, **changes)]}),
                             ["deploy/database.tf"])

    def test_invalid_analysis_retries_once_with_validation_feedback(self):
        state = {"slug": "example", "item": "Task", "pr_url": PR,
                 "base_sha": SHA, "archive_path": "archive"}
        ctx = {"head": HEAD, "paths": ["deploy/database.tf"], "diff": "+RDS",
               "planned": "Use existing DB", "complete": True}
        invalid = SimpleNamespace(output=json.dumps({"decisions": [
            dict(DECISION, paths=["deploy/database.tf:12"])]}))
        valid = SimpleNamespace(output=json.dumps({"decisions": [DECISION]}))
        with patch.object(main.architecture_report, "collect", return_value=ctx), \
             patch.object(main.agent_runner, "run", side_effect=[invalid, valid]) as agent, \
             patch.object(main, "email") as send, patch.object(main, "save_state"), \
             patch.object(main.diagnostics, "report", return_value=Path("report.txt")):
            main._notify_architecture(state)
        self.assertEqual(agent.call_count, 2)
        self.assertIn("exact changed-file paths", agent.call_args.args[0])
        send.assert_called_once()
        self.assertEqual(state["architecture_report"]["decisions"], [DECISION])

    def test_failed_retry_preserves_previous_report_and_does_not_send(self):
        previous = {"head": "c" * 40, "decisions": [DECISION]}
        state = {"base_sha": SHA, "archive_path": "archive", "pr_url": PR,
                 "architecture_report": previous}
        ctx = {"head": HEAD, "paths": ["deploy/database.tf"], "diff": "+RDS",
               "planned": "Use existing DB", "complete": True}
        for output in ("not json", json.dumps({"decisions": [dict(DECISION, planned="false")]})):
            with self.subTest(output=output), \
                 patch.object(main.architecture_report, "collect", return_value=ctx), \
                 patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=output)) as agent, \
                 patch.object(main, "email") as send, patch.object(main, "save_state") as save, \
                 self.assertLogs(main.log, level="WARNING"):
                main._notify_architecture(state, update=True)
            self.assertEqual(agent.call_count, 2)
            send.assert_not_called()
            save.assert_not_called()
            self.assertEqual(state["architecture_report"], previous)

    def test_notice_is_sent_once_and_subsequent_change_is_only_delta(self):
        state = {"slug": "example", "item": "Task", "pr_url": PR,
                 "base_sha": SHA, "archive_path": "openspec/changes/archive/2026-09-29-example"}
        ctx = {"head": HEAD, "paths": ["deploy/database.tf"], "diff": "+RDS",
               "planned": "## design\nUse existing DB", "complete": True}
        answer = SimpleNamespace(output=json.dumps({"decisions": [DECISION]}))
        with patch.object(main.architecture_report, "collect", return_value=ctx), \
             patch.object(main.agent_runner, "run", return_value=answer) as agent, \
             patch.object(main, "email") as send, patch.object(main, "save_state"):
            main._notify_architecture(state)
            main._notify_architecture(state)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(agent.call_count, 1)
            ctx = dict(ctx, head="c" * 40)
            with patch.object(main.architecture_report, "collect", return_value=ctx):
                main._notify_architecture(state, update=True)
                self.assertEqual(send.call_count, 1)
                agent.return_value = SimpleNamespace(output=json.dumps({"decisions": [
                    dict(DECISION, impact="Adds a new privileged deployment boundary")]}))
                ctx["head"] = "d" * 40
                main._notify_architecture(state, update=True)
        self.assertEqual(send.call_count, 2)
        self.assertIn("Architecture update", send.call_args.args[2])
        self.assertEqual(state["architecture_report"]["head"], "d" * 40)

    def test_analysis_failure_is_logged_without_a_false_empty_notice(self):
        state = {"base_sha": SHA, "archive_path": "archive", "pr_url": PR}
        with patch.object(main.architecture_report, "collect", side_effect=ValueError("invalid")), \
             patch.object(main, "email") as send:
            main._notify_architecture(state)
        send.assert_not_called()
        self.assertNotIn("architecture_report", state)

    def test_pr_announcement_precedes_automated_review_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            archive = repo / "openspec/changes/archive/2026-09-29-example"
            archive.mkdir(parents=True)
            state = {"state": "OPEN_PR", "slug": "example", "item": "Task",
                     "branch": "bot-example", "archive_path": "openspec/changes/archive/2026-09-29-example",
                     "pr_url": PR, "has_code_review": True}
            order = []
            def fake_git(*args):
                return "archived file" if args[0] == "ls-tree" else ""
            with patch.object(main.config, "REPO_PATH", repo), \
                  patch.object(main, "git", side_effect=fake_git), \
                  patch.object(main, "_publish_existing_pr"), patch.object(main, "_verify_pr_publication"), \
                  patch.object(main, "trail"), patch.object(main.task_source, "note_pr"), \
                 patch.object(main, "_notify_architecture",
                              side_effect=lambda *_: order.append("architecture")), \
                 patch.object(main, "_enter_review_wait",
                              side_effect=lambda *_: order.append("review")):
                main.do_open_pr(state)
        self.assertEqual(order, ["architecture", "review"])
