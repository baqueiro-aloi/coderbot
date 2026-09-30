from pathlib import Path
import subprocess
import tempfile
import unittest

from execution_identity import snapshot


class IdentityTests(unittest.TestCase):
    def test_content_changes_without_status_change_and_document_scope(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "app.py").write_text("first")
            (repo / "README.md").write_text("doc")
            before = snapshot(repo, ["app.py"])
            (repo / "app.py").write_text("second")
            after = snapshot(repo, ["app.py"])
            self.assertNotEqual(before, after)
            (repo / "README.md").write_text("new doc")
            self.assertEqual(snapshot(repo, ["app.py"]), after)
            (repo / "extra.py").write_text("new input")
            self.assertNotEqual(snapshot(repo), snapshot(repo, ["app.py"]))

    def test_sensitive_files_and_cache_are_not_snapshot_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            before = snapshot(repo)
            (repo / ".env").write_text("TOKEN=secret")
            (repo / "node_modules").mkdir()
            (repo / "node_modules/file.js").write_text("cache")
            self.assertEqual(before, snapshot(repo))
