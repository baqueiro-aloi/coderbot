from pathlib import Path
import subprocess
import tempfile
import unittest

from check_baseline import compare, worktree


class BaselineTests(unittest.TestCase):
    def test_semantic_error_difference_is_regression_and_unknown_blocks(self):
        base = {"status": "fail", "failures": {"test": "AssertionError: expected 2"}}
        same = compare(base, base)
        self.assertEqual(same["preexisting"], ["test"])
        changed = {"status": "fail", "failures": {"test": "AssertionError: expected 3"}}
        self.assertEqual(compare(changed, base)["regressions"], ["test"])
        self.assertEqual(compare(base, {"status": "infrastructure"})["status"], "indeterminate")
    def test_worktree_is_pinned_and_removed_after_failure(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / "repo"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "app").write_text("baseline")
            subprocess.run(["git", "add", "app"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                "commit", "-qm", "baseline"], cwd=repo, check=True)
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True,
                                 capture_output=True, check=True).stdout.strip()
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with worktree(repo, sha, Path(root) / "data") as path:
                    self.assertEqual((path / "app").read_text(), "baseline")
                    raise RuntimeError("test failure")
            self.assertFalse(path.exists())
