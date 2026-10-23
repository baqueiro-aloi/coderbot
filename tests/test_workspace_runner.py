"""Controlled workspace lifecycle: synthetic Git repos and fake external adapters."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main
import workspace_runner as runner
from execution_identity import snapshot
from workspace import WorkspaceError, discover
from workspace_state import bind_and_validate
from tests.test_workspace import git, repository


class WorkspaceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "workspace"
        self.root.mkdir()
        self.data = self.root.parent / "data"
        self.data.mkdir()
        self.api = repository(self.root / "api", remote="https://github.com/example/api.git")
        self.ui = repository(self.root / "ui", remote="https://github.com/example/ui.git")
        self.unused = repository(self.root / "unused", remote="https://github.com/example/unused.git")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {"REPO_PATH": self.root, "DATA_DIR": self.data, "STATE_PATH": self.data / "state.json",
                            "HOLDS_PATH": self.data / "holds.json", "TARGET_MODE": "workspace",
                            "WORKSPACE_MANIFEST": None}.items():
            self.stack.enter_context(patch.object(main.config, name, value))
        self.stack.enter_context(patch.object(main, "email", Mock()))
        self.stack.enter_context(patch.object(main, "trail", Mock()))
        self.stack.enter_context(patch.object(main, "announce_milestone", Mock()))
        self.stack.enter_context(patch.object(main, "task_source", Mock()))
        self.stack.enter_context(patch.object(main, "_ensure_task_language", Mock()))
        self.context = discover(self.root)
        self.state = bind_and_validate({"state": "IDLE"}, self.context)
        self.state.update(item="Feature", slug="feature", branch="bot-feature", state="IMPLEMENTING",
                          execution_task_id="task", session_id="session")
        self.state["workspace"]["baseline"] = runner.inspect_repositories(self.context)

    def edit(self, path):
        git(path, "checkout", "-b", "bot-feature")
        (path / "source.txt").write_text("feature")
        git(path, "add", "source.txt")
        git(path, "commit", "-m", "feature")

    def records(self):
        runner.record_changes(self.state, self.context, self.state["workspace"]["baseline"])

    def verified(self):
        self.state["workspace"]["verified_snapshot"] = snapshot(self.root)

    def test_full_workspace_writes_and_automatic_subset_tracking(self):
        before = runner.inspect_repositories(self.context)
        self.edit(self.api)
        self.edit(self.ui)
        runner.record_changes(self.state, self.context, before)
        self.assertEqual(set(self.state["workspace"]["repositories"]), {"api", "ui"})
        self.assertEqual(git(self.unused, "branch", "--show-current"), "main")
        self.assertIn("All files and child repositories", runner.instructions(self.state, self.context))
        self.assertFalse((self.root / ".git").exists())

    def test_pick_only_accepts_actual_backlog_item_and_preserves_branches(self):
        self.state = {"state": "IDLE"}
        main.task_source.list_pending_items.return_value = [
            {"text": "Feature", "id": "MC-1", "detail": "Change API and UI"}]
        main.task_source.claim_task.return_value = True
        with patch.object(main.gmail_client, "open_thread", return_value="C123:1"):
            runner.pick(self.state)
        self.assertEqual(self.state["item_id"], "MC-1")
        self.assertEqual(self.state["state"], "EXPLORING")
        self.assertEqual(git(self.api, "branch", "--show-current"), "main")
        self.assertEqual(self.state["workspace"]["repositories"], {})

    def test_all_prs_merged_finishes_only_verified_feature(self):
        self.edit(self.api)
        self.edit(self.ui)
        self.records()
        self.verified()
        for name, record in self.state["workspace"]["repositories"].items():
            record.update(pr_url=f"https://github.com/example/{name}/pull/1",
                          delivered_sha=git(self.root / name, "rev-parse", "HEAD"))
        def merged(repo, *args):
            value = self.publication(repo, self.state["workspace"]["repositories"][repo.relative_path])
            value["state"] = "MERGED"
            return json.dumps(value)
        with patch.object(runner, "gh", side_effect=merged), patch.object(main, "_finish_task") as finish:
            runner.poll_prs(self.state)
        finish.assert_called_once()
        self.assertFalse(finish.call_args.kwargs["reset_repo"])

    def test_hold_saves_workspace_without_reset_and_resume_uses_saved_context(self):
        with patch.object(main, "_release_credentials"), patch.object(main, "_publish_progress"), \
             patch.object(main, "_reset_to_base_branch") as reset, patch.object(main, "_commit_pending_work") as commit:
            main._hold_task(self.state, "C123:1")
        reset.assert_not_called()
        commit.assert_not_called()
        hold = json.loads(main.config.HOLDS_PATH.read_text())[0]
        self.assertIn("workspace", hold["saved"])
        self.assertEqual(self.state["state"], "IDLE")

    def test_turn_records_late_edits_and_shared_local_journal(self):
        (self.root / "scripts").mkdir()
        file = self.root / "scripts/run.sh"
        file.write_text("echo before\n")
        def invoke(prompt):
            self.assertIn("no repository-selection permission gate", prompt)
            self.edit(self.api)
            file.write_text("echo after\n")
            return SimpleNamespace(session_id="new-session", output="done")
        with patch.object(main.agent_runner, "resume", side_effect=lambda sid, prompt: invoke(prompt)):
            runner.turn(self.state, "Implement")
        self.assertIn("api", self.state["workspace"]["repositories"])
        self.assertEqual(self.state["session_id"], "new-session")
        edit = self.state["workspace"]["local_edits"][0]
        self.assertEqual(Path(edit["journal"]).stat().st_mode & 0o777, 0o600)
        file.write_text("user changed it\n")
        with self.assertRaisesRegex(WorkspaceError, "overwrite"):
            runner.restore_local(self.context, edit["journal"])
        file.write_text("echo after\n")
        runner.restore_local(self.context, edit["journal"])
        self.assertEqual(file.read_text(), "echo before\n")

    def test_secrets_not_journaled(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts/key.pem").write_text("private")
        (self.root / ".env").write_text("SECRET=secret")
        self.assertNotIn(".env", runner._shared_files(self.context))
        self.assertNotIn("scripts/key.pem", runner._shared_files(self.context))

    def test_snapshot_includes_dependency_and_local_changes_not_env_or_outputs(self):
        before = snapshot(self.root)
        (self.unused / "source.txt").write_text("dependency changed")
        self.assertNotEqual(snapshot(self.root), before)
        before = snapshot(self.root)
        (self.root / "docker-compose.yaml").write_text("services: {}")
        self.assertNotEqual(snapshot(self.root), before)
        before = snapshot(self.root)
        (self.root / ".env").write_text("SECRET=private")
        self.assertEqual(snapshot(self.root), before)

    def test_checks_run_again_when_another_repository_changes(self):
        import checks
        import check_plan
        store = main.phase_checkpoint.store()
        check = check_plan.Check("integration", ["sh", "-c", "echo OK"], cwd=".")
        first = checks.execute(check, self.root, store, "task")
        second = checks.execute(check, self.root, store, "task")
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        (self.ui / "source.txt").write_text("changed")
        third = checks.execute(check, self.root, store, "task")
        self.assertFalse(third["reused"])

    def test_unsafe_harness_rejected_without_execution(self):
        import check_plan
        e2e = self.root / "e2e"
        e2e.mkdir()
        (e2e / "run.sh").write_text("docker compose down --volumes\n")
        with self.assertRaisesRegex(WorkspaceError, "destructive"):
            runner.validate_check(self.context, check_plan.Check("e2e", ["./run.sh"], cwd="e2e"))

    def publication(self, repo, record):
        return {"url": f"https://github.com/example/{repo.relative_path}/pull/1", "state": "OPEN",
                "headRefName": record["branch"], "baseRefName": repo.base_branch,
                "headRefOid": git(repo.path, "rev-parse", "HEAD"), "isCrossRepository": False}

    def test_multiple_prs_and_partial_merge_do_not_finish_feature(self):
        self.edit(self.api)
        self.edit(self.ui)
        self.records()
        self.verified()
        def github(repo, *args):
            record = self.state["workspace"]["repositories"][repo.relative_path]
            if args[1] == "list":
                return "[]"
            if args[1] == "create":
                return self.publication(repo, record)["url"]
            return json.dumps(self.publication(repo, record))
        real_git = runner.git
        def git_no_push(repo, *args):
            return "" if args[0] == "push" else real_git(repo, *args)
        with patch.object(runner, "git", side_effect=git_no_push), patch.object(runner, "gh", side_effect=github):
            runner.publish(self.state)
        self.assertEqual(self.state["state"], "WAIT_MERGE")
        self.assertEqual(main.email.call_count, 2)
        self.assertTrue(all(record["announced"] for record in self.state["workspace"]["repositories"].values()))
        def statuses(repo, *args):
            value = self.publication(repo, self.state["workspace"]["repositories"][repo.relative_path])
            value.update(state="MERGED" if repo.relative_path == "api" else "OPEN", mergeable="MERGEABLE")
            return json.dumps(value)
        with patch.object(runner, "gh", side_effect=statuses), \
             patch.object(main, "unresolved_review_threads", return_value=[]), \
             patch.object(main, "handle_wait"), patch.object(main, "_finish_task") as finish:
            runner.poll_prs(self.state)
        finish.assert_not_called()
        self.assertEqual(self.state["workspace"]["repositories"]["api"]["merge"]["status"], "MERGED")

    def test_restart_reconciles_accepted_pr_without_duplicate_create(self):
        self.edit(self.api)
        self.records()
        self.verified()
        record = self.state["workspace"]["repositories"]["api"]
        calls = []
        def github(repo, *args):
            calls.append(args[1])
            if args[1] == "list":
                return json.dumps([self.publication(repo, record)])
            return json.dumps(self.publication(repo, record))
        real_git = runner.git
        with patch.object(runner, "git", side_effect=lambda repo, *args: "" if args[0] == "push" else real_git(repo, *args)), \
             patch.object(runner, "gh", side_effect=github):
            runner.publish(self.state)
        self.assertNotIn("create", calls)
        self.assertEqual(self.state["workspace"]["repositories"]["api"]["pr_url"],
                         "https://github.com/example/api/pull/1")

    def test_abort_and_finish_preserve_files_and_do_not_run_root_git(self):
        with patch.object(main, "_reset_to_base_branch") as reset, \
             patch.object(main, "_release_credentials"), patch.object(main, "_publish_progress"):
            main._abort_and_reset(self.state, "Stop")
        reset.assert_not_called()
        self.assertEqual(self.state["state"], "IDLE")
        self.assertNotIn("workspace", self.state)
        self.assertEqual(git(self.api, "branch", "--show-current"), "main")

    def test_verification_requires_shared_check_and_binds_evidence(self):
        self.edit(self.api)
        self.records()
        self.state["reported_check_plan"] = [{"id": "integration", "argv": ["sh", "-c", "echo OK"], "cwd": "."}]
        self.state["state"] = "VERIFYING"
        self.state["workspace"]["reviewed_snapshot"] = snapshot(self.root)
        runner.verify(self.state)
        self.assertEqual(self.state["state"], "ARCHIVING")
        self.assertEqual(self.state["workspace"]["verified_snapshot"], snapshot(self.root))


if __name__ == "__main__":
    unittest.main()
