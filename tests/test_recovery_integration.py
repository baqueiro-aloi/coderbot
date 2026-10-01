from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"task_source": Mock(), "gmail_client": Mock(), "gdoc_client": Mock()}):
    import main
from execution_store import ExecutionStore
import repo_provenance
import recovery


class RecoveryIntegration(unittest.TestCase):
    def test_bot_test_repair_commits_verifies_and_resumes_archival(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / "repo"
            repo.mkdir()
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
            git("init")
            file = repo / "test_repair.py"
            file.write_text("base")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
            store = ExecutionStore(Path(root) / "db")
            state = {"item": "task", "state": "ARCHIVING", "branch": "feature", "session_id": "session"}
            state["execution_task_id"] = store.task_identity(state, repo)
            initial = repo_provenance.inspect(repo)
            repo_provenance.record(store, state, repo, initial=True)
            file.write_text("repaired")
            repo_provenance.record_turn(store, state, repo, initial, repo_provenance.inspect(repo))
            recovery.begin(store, state, repo, "test repair pending", "ARCHIVING")
            def repair(*args):
                self.assertIn("test_repair.py", args[1])
                git("add", "test_repair.py")
                git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "repair")
                return SimpleNamespace(session_id="session", output="Verified repair", question=None, attachments=[])
            with patch.object(main.config, "REPO_PATH", repo), \
                 patch.object(main.phase_checkpoint, "store", return_value=store), \
                 patch.object(main.agent_runner, "resume", side_effect=repair), \
                 patch.object(main.final_checks, "run", return_value={"status": "pass", "checks": []}) as checks, \
                 patch.object(main, "save_state"), patch.object(main, "email") as email:
                main.do_recover(state)
            self.assertEqual(state["state"], "ARCHIVING")
            self.assertFalse(repo_provenance.inspect(repo)["files"])
            checks.assert_called_once()
            email.assert_not_called()

    def test_interrupted_merge_is_visible_without_altering_index(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*args, check=True):
                return subprocess.run(["git", *args], cwd=root, capture_output=True, check=check)
            git("init")
            file = Path(root) / "file.txt"
            def commit(text):
                file.write_text(text)
                git("add", ".")
                git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", text)
            commit("base")
            git("checkout", "-b", "other")
            commit("other")
            git("checkout", "-b", "feature", "HEAD~1")
            commit("feature")
            git("merge", "other", check=False)
            state = repo_provenance.inspect(root)
            self.assertIn("MERGE_HEAD", state["operations"])
            self.assertEqual(state["files"]["file.txt"]["status"], "UU")
            self.assertEqual(repo_provenance.inspect(root), state)
            task = {"item": "task", "branch": "feature", "execution_task_id": "a" * 64}
            # Preserve unresolved conflict content in its original checkout; recreate
            # merge intent in isolation rather than copying conflict markers as a fix.
            isolated = recovery.isolate(task, root, Path(root) / "data", [])
            self.assertEqual(repo_provenance.inspect(root)["index"], state["index"])
            self.assertTrue(task["isolated_merge_heads"])
            self.assertFalse(repo_provenance.inspect(isolated)["operations"])
