import json
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main
import task_phases


class TaskPhaseTests(unittest.TestCase):
    def test_implementation_can_defer_only_explicit_controller_tasks(self):
        for deterministic in (False, True):
            with self.subTest(deterministic=deterministic), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                path.write_text("- [x] 1. Implementation\n- [ ] 2. [codebot:final-checks] Run suite\n")
                state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main.config, "DETERMINISTIC_CHECKS", deterministic), \
                     patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                         "progress": {"total": 2, "complete": 1, "remaining": 1}})), \
                     patch.object(main, "_scrub_evidence_from_repo", return_value=[]), patch.object(main, "trail"), \
                     patch.object(main, "_enter_stuck") as stuck, patch.object(main, "announce_milestone") as announce:
                    main._complete_implementation(state, SimpleNamespace(output="Done", attachments=[]))
                if deterministic:
                    self.assertEqual(state["state"], "VERIFYING")
                    announce.assert_called_once()
                    stuck.assert_not_called()
                else:
                    stuck.assert_called_once()
                    announce.assert_not_called()

    def test_partial_turns_in_both_paths_preserve_evidence_and_only_final_turn_announces(self):
        for via_reply in (False, True):
            with self.subTest(via_reply=via_reply), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                path.write_text("- [x] 1. First change\n- [ ] 2. Second change\n")
                evidence = Path(root) / "result.txt"
                evidence.write_text("focused checks passed")
                state = {"state": "IMPLEMENTING", "slug": "task", "item": "task",
                         "branch": "feature", "session_id": "session"}
                partial = SimpleNamespace(output="First change done\nE2E_SPEC: first.spec.ts",
                                          attachments=[str(evidence)])
                complete = SimpleNamespace(output="Second change done\nE2E_SPEC: second.spec.ts",
                                           attachments=[])
                saved = []
                def instructions(*args):
                    progress = task_phases.inspect(root, "task")
                    remaining = progress["total"] - progress["complete"]
                    return json.dumps({"state": "ready" if remaining else "all_done", "progress": {
                        "total": progress["total"], "complete": progress["complete"], "remaining": remaining}})
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main, "_run_checked", side_effect=instructions), \
                     patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                     patch.object(main, "content_snapshot", return_value="snapshot"), \
                     patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
                     patch.object(main, "save_state", side_effect=lambda s: saved.append(json.loads(json.dumps(s)))), \
                     patch.object(main, "announce_milestone") as announce, \
                     patch.object(main.agent_runner, "resume", side_effect=[partial, complete]) as resume:
                    if via_reply:
                        main._continue_implementing(state, partial)
                    else:
                        main.do_implement(state)
                    self.assertEqual(state["state"], "IMPLEMENTING")
                    self.assertEqual(state["implementation_turn"], 1)
                    announce.assert_not_called()
                    self.assertEqual(state["implementation_attachments"], [str(evidence)])
                    state = saved[-1]  # restart resumes the saved continuation
                    path.write_text("- [x] 1. First change\n- [x] 2. Second change\n")
                    if via_reply:
                        main._continue_implementing(state, complete)
                    else:
                        main.do_implement(state)
                        self.assertIn("Implementation continuation: 1", resume.call_args.args[1])
                        self.assertNotEqual(resume.call_args_list[0].args[1], resume.call_args.args[1])
                    self.assertEqual(state["state"], "VERIFYING")
                    self.assertEqual(len(state["e2e_specs"]), 2)
                    announce.assert_called_once()

    def test_missing_empty_or_inconsistent_plan_never_advances(self):
        for content, progress in ((None, {}), ("No tasks", {}),
                ("- [ ] 1. Pending\n", {"total": 1, "complete": 1, "remaining": 0})):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                if content is not None:
                    path.write_text(content)
                state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main, "_run_checked", return_value=json.dumps({"state": "all_done", "progress": progress})), \
                     patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                     patch.object(main, "_enter_stuck") as stuck, patch.object(main, "announce_milestone") as announce:
                    main._complete_implementation(state, SimpleNamespace(output="Finished", attachments=[]))
                stuck.assert_called_once()
                announce.assert_not_called()
                self.assertNotEqual(state["state"], "VERIFYING")

    def test_no_progress_pauses_but_partial_repository_changes_reset_counter(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Large change\n")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
            result = SimpleNamespace(output="Still working", attachments=[])
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "QUALITY_GATE_MAX_ROUNDS", 2), \
                 patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                     "progress": {"total": 1, "complete": 0, "remaining": 1}})), \
                 patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                 patch.object(main, "content_snapshot", side_effect=["a", "a", "b", "b", "b"]), \
                 patch.object(main, "save_state"), patch.object(main, "email") as email, \
                 patch.object(main.diagnostics, "report", return_value=Path(root) / "report.txt"):
                for _ in range(3):
                    main._complete_implementation(state, result)
                self.assertEqual(state["implementation_no_progress"], 0)
                for _ in range(2):
                    main._complete_implementation(state, result)
            self.assertEqual(state["state"], "WAIT_REPLY")
            self.assertIn("Large change", state["pending_question"])
            email.assert_called_once()

    def test_new_continuation_does_not_replay_completed_partial_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Pending\n")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task", "branch": "feature", "session_id": "sid"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DATA_DIR", Path(root) / "data"), \
                 patch.object(main.config, "AGENT", "opencode"), \
                 patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                     "progress": {"total": 1, "complete": 0, "remaining": 1}})), \
                 patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                 patch.object(main, "handle_result", return_value=False), \
                 patch.object(main, "save_state"), patch.object(main, "content_snapshot", return_value="a"), \
                 patch.object(main.agent_runner, "_opencode", return_value=main.agent_runner.OpenCodeResult("sid", "partial")) as run:
                main.agent_runner.set_task_context(state)
                try:
                    main.do_implement(state)
                    reloaded = json.loads(json.dumps(state))
                    main.agent_runner.set_task_context(reloaded)
                    main.do_implement(reloaded)
                finally:
                    main.agent_runner.set_task_context(None)
            self.assertEqual(run.call_count, 2)

    def test_pending_implementation_returns_to_work_without_consuming_gate_retries(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Implement cancellation\n- [ ] 2. [codebot:final-checks] Run suite\n")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"):
                main._complete_verify(state, SimpleNamespace(output="incomplete"))
            self.assertEqual(state["state"], "IMPLEMENTING")
            self.assertNotIn("verify_round", state)
            self.assertIn("Implement cancellation", state["implementation_feedback"])

    def test_explicit_controller_task_can_wait_until_final_checks_pass(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [x] 1. Implement\n- [ ] 2. [codebot:final-checks] Run suite\n")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            output = 'QUALITY_GATE: ' + json.dumps({"status": "pass", "openspec": "pass",
                "commands": ["focused: pass"], "tasks": "1/2", "deferred": 1})
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
                 patch.object(main, "_run_checked", side_effect=["valid", json.dumps({"state": "ready",
                     "progress": {"total": 2, "complete": 1, "remaining": 1}})]):
                main._complete_verify(state, SimpleNamespace(output=output))
            self.assertEqual(state["state"], "INTERNAL_REVIEW")
            self.assertEqual(len(task_phases.inspect(root, "task")["final_checks"]), 1)
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), patch.object(main, "save_state"), \
                 patch.object(main, "announce_milestone"), \
                 patch.object(main, "_gate_failed"), \
                 patch.object(main.final_checks, "run", return_value={"status": "indeterminate", "checks": []}):
                main.do_e2e(state)
            self.assertEqual(len(task_phases.inspect(root, "task")["final_checks"]), 1)
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), patch.object(main, "save_state"), \
                 patch.object(main, "announce_milestone"), \
                 patch.object(main.final_checks, "run", return_value={"status": "pass", "checks": []}):
                main.do_e2e(state)
            self.assertEqual(task_phases.inspect(root, "task")["complete"], 2)
            self.assertEqual(state["state"], "ARCHIVING")

    def test_incomplete_count_cannot_pass_without_explicit_defer_count(self):
        output = 'QUALITY_GATE: ' + json.dumps({"status": "pass", "openspec": "pass",
            "commands": ["focused: pass"], "tasks": "1/2"})
        self.assertIsNone(main.parse_quality_gate(output)[0])
