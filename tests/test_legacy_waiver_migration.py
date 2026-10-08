from pathlib import Path
import tempfile
import unittest

from execution_store import ExecutionStore
import task_records


class LegacyWaiverMigrationTests(unittest.TestCase):
    def test_free_text_waiver_preserved_but_cannot_skip_check(self):
        with tempfile.TemporaryDirectory() as root:
            state = {'item': 'task', 'branch': 'branch', 'check_waivers': [
                {'scope': 'e2e:general', 'instruction': 'skip', 'snapshot': 'old'}]}
            task_records.migrate(state, ExecutionStore(Path(root) / 'execution.sqlite'), root)
            self.assertNotIn('check_waivers', state)
            self.assertEqual(state['legacy_validation_waivers'][0]['status'], 'legacy_unverified')
            restored = dict(state)
            task_records.migrate(restored, ExecutionStore(Path(root) / 'execution.sqlite'), root)
            self.assertEqual(len(restored['legacy_validation_waivers']), 1)
