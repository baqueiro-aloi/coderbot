import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from check_plan import Check
from private_secrets import PrivateSecrets, SecretUnavailable
import secret_safety


class PrivateSecretTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(secret_safety.clear)
        self.root = Path(self.temp.name)
        self.now = 100
        self.store = PrivateSecrets(self.root / 'private', clock=lambda: self.now)
        self.check = Check('live', [sys.executable, '-c', 'pass'], env_keys=['SERVICE_KEY'])

    def provision(self):
        return self.store.provision('synthetic-private-value', task_id='task', check=self.check,
                                    env_key='SERVICE_KEY', ttl=10)

    def test_permissions_and_recovery(self):
        handle = self.provision()
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store._path(handle).stat().st_mode & 0o777, 0o600)
        recovered = PrivateSecrets(self.store.directory, clock=lambda: self.now)
        self.assertEqual(recovered.resolve(handle, task_id='task', check=self.check),
                         ('SERVICE_KEY', 'synthetic-private-value'))
        self.assertNotIn('synthetic-private-value', secret_safety.redact('synthetic-private-value'))

    def test_exact_task_and_operation_binding(self):
        handle = self.provision()
        for task, check in [('other', self.check), ('task', Check('live', ['different'], env_keys=['SERVICE_KEY']))]:
            with self.assertRaises(SecretUnavailable):
                self.store.resolve(handle, task_id=task, check=check)

    def test_expiration_removes_record_and_preserves_other_work(self):
        handle = self.provision()
        unrelated = self.root / 'human.txt'
        unrelated.write_text('preserve')
        self.now = 110
        with self.assertRaises(SecretUnavailable):
            self.store.resolve(handle, task_id='task', check=self.check)
        self.assertFalse(self.store._path(handle).exists())
        self.assertEqual(unrelated.read_text(), 'preserve')

    def test_symlinks_loose_permissions_and_traversal_rejected(self):
        handle = self.provision()
        self.store._path(handle).chmod(0o644)
        with self.assertRaises(SecretUnavailable):
            self.store.resolve(handle, task_id='task', check=self.check)
        self.store._path(handle).unlink()
        self.store._path(handle).symlink_to(self.root / 'outside')
        with self.assertRaises(SecretUnavailable):
            self.store.resolve(handle, task_id='task', check=self.check)
        with self.assertRaises(SecretUnavailable):
            self.store.revoke('../human')

    def test_injects_only_child_environment_not_parent_or_argv(self):
        code = "import os; print(os.environ.get('SERVICE_KEY', 'missing'))"
        check = Check('child', [sys.executable, '-c', code], env_keys=['SERVICE_KEY'])
        handle = self.store.provision('synthetic-private-value', task_id='task', check=check,
                                     env_key='SERVICE_KEY', ttl=10)
        with self.store.environment([handle], task_id='task', check=check, environ={}) as env:
            result = subprocess.run(check.argv, env=env, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'synthetic-private-value')
        self.assertNotIn('SERVICE_KEY', env)
        self.assertNotIn('synthetic-private-value', ' '.join(check.argv))

    def test_partial_write_cleanup_and_missing_handle(self):
        path = self.store._path('a' * 32)
        path.write_text('{')
        path.chmod(0o600)
        self.store.cleanup()
        self.assertFalse(path.exists())
        with self.assertRaises(SecretUnavailable):
            self.store.resolve('a' * 32, task_id='task', check=self.check)

    def test_duplicate_bindings_rejected(self):
        handle = self.provision()
        with self.assertRaises(SecretUnavailable), self.store.environment(
                [handle, handle], task_id='task', check=self.check):
            pass

    def test_common_runner_injects_and_redacts_before_reports_and_sqlite(self):
        from checks import execute
        from execution_store import ExecutionStore
        repo = self.root / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        db = ExecutionStore(self.root / 'data' / 'execution.sqlite')
        private = PrivateSecrets(db.path.parent / 'private-secrets')
        check = Check('child', [sys.executable, '-c',
            "import os; print(os.environ['SERVICE_KEY'])"], env_keys=['SERVICE_KEY'])
        handle = private.provision('synthetic-private-value', task_id='task', check=check,
                                   env_key='SERVICE_KEY')
        result = execute(check, repo, db, 'task', secret_handles=[handle])
        self.assertIn('[REDACTED]', Path(result['report']).read_text())
        with db.connection() as connection:
            self.assertNotIn('synthetic-private-value', connection.execute('SELECT data FROM check_run').fetchone()[0])

    def test_new_private_credential_invalidates_only_its_check_cache(self):
        from checks import execute
        from execution_store import ExecutionStore
        repo = self.root / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        db = ExecutionStore(self.root / 'data' / 'execution.sqlite')
        private = PrivateSecrets(db.path.parent / 'private-secrets')
        check = Check('private', [sys.executable, '-c', 'pass'], env_keys=['SERVICE_KEY'])
        first = private.provision('first-private-value', task_id='task', check=check, env_key='SERVICE_KEY')
        initial = execute(check, repo, db, 'task', secret_handles=[first])
        self.assertFalse(initial['reused'])
        second = private.provision('second-private-value', task_id='task', check=check, env_key='SERVICE_KEY')
        changed = execute(check, repo, db, 'task', secret_handles=[second])
        self.assertFalse(changed['reused'])
        self.assertNotEqual(initial['identity'], changed['identity'])
