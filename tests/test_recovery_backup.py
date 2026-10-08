from pathlib import Path
import subprocess
import tempfile
import unittest

from recovery import backup


class RecoveryBackupTests(unittest.TestCase):
    def test_exact_human_and_untracked_bytes_preserved_privately_without_reset(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'app').write_text('base')
            subprocess.run(['git', 'add', 'app'], cwd=repo, check=True)
            subprocess.run(['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.test',
                            'commit', '-qm', 'base'], cwd=repo, check=True)
            (repo / 'app').write_text('human')
            (repo / 'secret.txt').write_text('synthetic-backup-secret')
            destination = backup(repo, Path(root) / 'data')
            self.assertEqual((destination / 'files/app').read_text(), 'human')
            self.assertEqual((destination / 'files/secret.txt').read_text(), 'synthetic-backup-secret')
            self.assertEqual((destination / 'files/secret.txt').stat().st_mode & 0o777, 0o600)
            self.assertEqual((repo / 'app').read_text(), 'human')
            self.assertEqual((repo / 'secret.txt').read_text(), 'synthetic-backup-secret')
