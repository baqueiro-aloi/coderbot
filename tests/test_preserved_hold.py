import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import main
import repo_provenance
from execution_store import ExecutionStore


class PreservedHoldTests(unittest.TestCase):
    def test_hold_never_stages_unattributed_changes_or_secret(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', '-b', 'task', str(repo)], check=True)
            for key, value in (('user.name', 'test'), ('user.email', 'test@example.test')):
                subprocess.run(['git', 'config', key, value], cwd=repo, check=True)
            (repo / 'app.py').write_text('original')
            subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
            subprocess.run(['git', 'commit', '-qm', 'base'], cwd=repo, check=True)
            store = ExecutionStore(Path(root) / 'data/db')
            state = {'branch': 'task', 'state': 'IMPLEMENTING', 'item': 't'}
            repo_provenance.record(store, state, repo, initial=True)
            (repo / 'app.py').write_text('human edit')
            (repo / 'credential.txt').write_text('synthetic-secret')
            with patch.object(main.config, 'REPO_PATH', repo), \
                 patch.object(main.phase_checkpoint, 'store', return_value=store):
                notes = main._commit_pending_work(state)
            self.assertIn('protected', ' '.join(notes))
            staged = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=repo,
                                    capture_output=True, text=True, check=True).stdout
            self.assertEqual(staged, '')
            self.assertEqual((repo / 'app.py').read_text(), 'human edit')
            self.assertEqual((repo / 'credential.txt').read_text(), 'synthetic-secret')
