from pathlib import Path
import subprocess
import tempfile
import unittest

from execution_store import ExecutionStore
import recovery
import repo_provenance


class RecoveryWorktreeTests(unittest.TestCase):
    def test_isolation_keeps_original_index_and_copies_owned_repairs(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / "repo"
            repo.mkdir()
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
            git("init")
            own = repo / "test with spaces.py"
            own.write_text("base")
            foreign = repo / "foreign.py"
            foreign.write_text("base")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
            foreign.write_text("user work")
            state = {"item": "task", "branch": "feature"}
            store = ExecutionStore(Path(root) / "db")
            state["execution_task_id"] = store.task_identity(state, repo)
            repo_provenance.record(store, state, repo, initial=True)
            turn_before = repo_provenance.inspect(repo)
            own.write_text("bot repair")
            git("add", own.name)
            before = repo_provenance.inspect(repo)
            repo_provenance.record_turn(store, state, repo, turn_before, before)
            owned, protected = recovery.ownership(store, state, repo, before)
            self.assertEqual(owned, [own.name])
            self.assertEqual(protected, [foreign.name])
            isolated = recovery.isolate(state, repo, Path(root) / "data", owned)
            self.assertEqual(repo_provenance.inspect(repo), before)
            self.assertEqual((isolated / own.name).read_text(), "bot repair")
            self.assertEqual((isolated / foreign.name).read_text(), "base")
            self.assertEqual(state["remote_branch"], "feature")
            self.assertEqual(recovery.isolate(state, repo, Path(root) / "data", owned), isolated)
