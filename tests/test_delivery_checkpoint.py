from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from delivery_checkpoint import step
from execution_store import ExecutionStore


class DeliveryTests(unittest.TestCase):
    def test_empty_result_is_retried_without_losing_history(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            action = Mock(side_effect=[[], ["video"]])
            self.assertEqual(step(store, "t", "s", "RECORD", action, validate=bool), [])
            self.assertEqual(step(store, "t", "s", "RECORD", action, validate=bool), ["video"])
            rows = store.list("delivery_step", "t")
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["status"] for r in rows}, {"retryable", "complete"})

    def test_legacy_empty_completion_and_missing_file_are_revalidated(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            step(store, "t", "s", "RECORD", lambda: [])
            action = Mock(return_value=["new"])
            self.assertEqual(step(store, "t", "s", "RECORD", action, validate=bool), ["new"])
            action.assert_called_once()
            self.assertEqual(len(store.list("delivery_step", "t")), 2)

    def test_pending_effect_reconciles_before_duplicate(self):
        from execution_identity import digest
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            store.put("delivery_step", task_id="t", identity=digest(["s", "NOTIFY"]), data={"step": "NOTIFY"})
            action = Mock()
            self.assertEqual(step(store, "t", "s", "NOTIFY", action, reconcile=lambda: "existing"), "existing")
            action.assert_not_called()
    def test_failed_upload_reuses_completed_recording(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            record = Mock(return_value=["video"])
            upload = Mock(side_effect=[RuntimeError("network"), "url"])
            step(store, "t", "snapshot", "RECORD", record)
            with self.assertRaises(RuntimeError):
                step(store, "t", "snapshot", "UPLOAD", upload)
            step(store, "t", "snapshot", "RECORD", record)
            self.assertEqual(step(store, "t", "snapshot", "UPLOAD", upload), "url")
            self.assertEqual(record.call_count, 1)
