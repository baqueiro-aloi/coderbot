"""_undo_premature_work against a real throwaway git repo."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main

main.config.STATE_PATH = pathlib.Path(tempfile.mkdtemp()) / "state.json"


class UndoPrematureWork(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
        self.env = env

        def sh(*args):
            return subprocess.run(["git", *args], cwd=self.repo, env=env, check=True,
                                  capture_output=True, text=True).stdout.strip()
        self.sh = sh
        sh("init", "-q", "-b", "main")
        (self.repo / "app.py").write_text("print(1)\n")
        (self.repo / "openspec").mkdir()
        (self.repo / "openspec" / "keep.md").write_text("spec\n")
        sh("add", "-A")
        sh("commit", "-q", "-m", "base")
        sh("checkout", "-q", "-b", "codebot-task")
        self.base = sh("rev-parse", "HEAD")
        self.patches = [patch.object(main.config, "REPO_PATH", self.repo),
                        patch.object(main.config, "BASE_BRANCH", "main")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def state(self):
        return {"branch": "codebot-task", "base_sha": self.base}

    def test_clean_tree_returns_no_note(self):
        self.assertEqual(main._undo_premature_work(self.state(), "EXPLORING"), "")

    def test_unattributed_commits_are_preserved_with_openspec(self):
        (self.repo / "app.py").write_text("print(2)\n")
        (self.repo / "openspec" / "change.md").write_text("new\n")
        self.sh("add", "-A")
        self.sh("commit", "-q", "-m", "premature")
        head = self.sh('rev-parse', 'HEAD')
        note = main._undo_premature_work(self.state(), "PROPOSING")
        self.assertIn("preserved", note)
        self.assertEqual(self.sh("rev-parse", "HEAD"), head)
        self.assertEqual((self.repo / "app.py").read_text(), "print(2)\n")
        self.assertTrue((self.repo / "openspec" / "change.md").exists())

    def test_paths_with_spaces_are_protected(self):
        (self.repo / "my file.txt").write_text("x\n")
        self.sh("add", "my file.txt")
        note = main._undo_premature_work(self.state(), "EXPLORING")
        self.assertIn("my file.txt", note)
        self.assertTrue((self.repo / "my file.txt").exists())
        self.assertTrue(self.sh("status", "--porcelain"))

    def test_wandering_onto_main_preserves_foreign_branch(self):
        self.sh("checkout", "-q", "main")
        (self.repo / "app.py").write_text("print(3)\n")
        self.sh("commit", "-q", "-am", "on main")
        # simulate origin/main at the base
        self.sh("update-ref", "refs/remotes/origin/main", self.base)
        note = main._undo_premature_work(self.state(), "EXPLORING")
        self.assertEqual(self.sh("rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertNotEqual(self.sh("rev-parse", "main"), self.base)
        self.assertIn("preserved", note)

    def test_human_edit_keeps_exact_bytes_and_index(self):
        (self.repo / 'app.py').write_text('human edit\n')
        self.sh('add', 'app.py')
        before = self.sh('diff', '--cached')
        main._undo_premature_work(self.state(), 'EXPLORING')
        self.assertEqual((self.repo / 'app.py').read_text(), 'human edit\n')
        self.assertEqual(self.sh('diff', '--cached'), before)


class AbortInProgressOps(UndoPrematureWork):
    def test_no_op_when_nothing_in_progress(self):
        with patch.object(main, "_git_quiet") as quiet:
            main._abort_in_progress_ops()
        quiet.assert_not_called()

    def test_aborts_a_real_merge_conflict(self):
        (self.repo / "app.py").write_text("branch\n")
        self.sh("commit", "-q", "-am", "branch change")
        self.sh("checkout", "-q", "main")
        (self.repo / "app.py").write_text("main\n")
        self.sh("commit", "-q", "-am", "main change")
        merge = subprocess.run(["git", "merge", "codebot-task"], cwd=self.repo, env=self.env,
                               capture_output=True, text=True)
        self.assertNotEqual(merge.returncode, 0)
        self.assertTrue((self.repo / ".git" / "MERGE_HEAD").exists())
        main._abort_in_progress_ops()
        self.assertFalse((self.repo / ".git" / "MERGE_HEAD").exists())
        self.assertEqual(self.sh("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
