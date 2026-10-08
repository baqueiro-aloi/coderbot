import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from check_plan import Check
from checks import execute
from execution_store import ExecutionStore


class EvidenceFreshnessTests(unittest.TestCase):
    def test_remote_evidence_expires_without_content_change(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            store = ExecutionStore(Path(root) / 'data/db')
            check = Check('remote', [sys.executable, '-c', "print('ok')"], kind='upstream',
                max_age_seconds=60, contract_version=2)
            result = execute(check, repo, store, 't')
            self.assertTrue(execute(check, repo, store, 't')['reused'])
            with patch('checks.time.time', return_value=result['finished'] + 61):
                self.assertFalse(execute(check, repo, store, 't')['reused'])

    def test_env_file_change_invalidates_without_recording_value(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            store = ExecutionStore(Path(root) / 'data/db')
            check = Check('local', [sys.executable, '-c', "print('ok')"])
            env = repo / '.env'
            env.write_text('SERVICE_KEY=synthetic-first\n')
            execute(check, repo, store, 't')
            self.assertTrue(execute(check, repo, store, 't')['reused'])
            env.write_text('SERVICE_KEY=synthetic-second\n')
            result = execute(check, repo, store, 't')
            self.assertFalse(result['reused'])
            self.assertEqual(result['repetition_reason'], 'environment_or_command_changed')
            with store.connection() as db:
                text = repr([tuple(r) for r in db.execute('SELECT * FROM check_run')])
            self.assertNotIn('synthetic-first', text)
            self.assertNotIn('synthetic-second', text)

    def test_unusable_results_are_not_cached(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            store = ExecutionStore(Path(root) / 'data/db')
            check = Check('empty', [sys.executable, '-c', "print('Ran 0 tests in 0.1s\\nOK')"],
                          reporter='unittest')
            self.assertEqual(execute(check, repo, store, 't')['status'], 'not_run')
            self.assertFalse(execute(check, repo, store, 't')['reused'])
