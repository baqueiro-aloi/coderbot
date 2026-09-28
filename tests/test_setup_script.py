"""The interactive setup launcher remains portable across supported shells."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SetupScriptTests(unittest.TestCase):
    def test_launcher_is_executable_and_shows_same_cli_on_sh_bash_zsh(self):
        script = ROOT / "scripts/setup.sh"
        self.assertTrue(script.stat().st_mode & 0o111)
        for shell in ("sh", "bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                proc = subprocess.run([shell, str(script), "--help"], cwd=ROOT,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("--text", proc.stdout)
                self.assertIn("Jira", proc.stdout)


if __name__ == "__main__":
    unittest.main()
