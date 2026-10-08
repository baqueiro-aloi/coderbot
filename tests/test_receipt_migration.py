from pathlib import Path
import tempfile
import unittest

from execution_store import ExecutionStore


class ReceiptMigrationTests(unittest.TestCase):
    def test_legacy_complete_receipt_is_preserved_but_not_reusable(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'execution.sqlite'
            store = ExecutionStore(path)
            store.put('check_run', task_id='task', id='legacy', status='complete', identity='same',
                      data={'result': {'status': 'pass'}})
            reopened = ExecutionStore(path)
            row = reopened.get('check_run', 'legacy')
            self.assertEqual(row['status'], 'complete')
            self.assertEqual(row['data']['result']['provenance'], 'legacy_unverified')
            self.assertIsNone(reopened.reusable_check('task', 'same'))

    def test_complete_receipt_with_required_identity_is_marked_verified(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'execution.sqlite'
            store = ExecutionStore(path)
            store.put('check_run', task_id='task', id='new', status='complete', identity='same', data={
                'result': {'status': 'pass', 'identity': 'same', 'content': 'content',
                           'environment': 'environment', 'check': 'unit'}})
            reopened = ExecutionStore(path)
            self.assertEqual(reopened.reusable_check('task', 'same')['id'], 'new')
