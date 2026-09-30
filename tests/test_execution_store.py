import tempfile
from pathlib import Path
import unittest

from execution_store import ENTITIES, ExecutionStore


class ExecutionStoreTests(unittest.TestCase):
    def test_interrupted_checks_are_not_reusable_and_tdd_is_durable(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            store.record_check("t", "input", result={"exit": 1}, status="running", tdd="RED")
            self.assertIsNone(store.reusable_check("t", "input"))
            store.interrupt_running("t")
            self.assertEqual(store.list("check_run", "t")[0]["status"], "interrupted")
            store.record_check("t", "green", result={"exit": 0}, tdd="GREEN")
            self.assertEqual(store.reusable_check("t", "green")["data"]["tdd"], "GREEN")

    def test_legacy_cursor_and_attempt_reconcile_after_crash(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            legacy = {"state": "VERIFYING", "branch": "feature", "base_sha": "abc"}
            first = store.begin_attempt(dict(legacy), root)
            restored = dict(legacy)
            self.assertEqual(store.begin_attempt(restored, root), first)
            task_id = restored["execution_task_id"]
            checkpoint = store.put("checkpoint", task_id=task_id, status="complete",
                data={"state_patch": {"state": "INTERNAL_REVIEW"}})
            store.reconcile(restored, root)
            self.assertEqual(restored["state"], "INTERNAL_REVIEW")
            self.assertEqual(restored["execution_checkpoint_id"], checkpoint)

    def test_all_entities_survive_reopening_and_migration(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "execution.sqlite"
            store = ExecutionStore(path)
            ids = {e: store.put(e, task_id="task", data={"value": e}, status="complete") for e in ENTITIES}
            reopened = ExecutionStore(path)
            for entity, id in ids.items():
                self.assertEqual(reopened.get(entity, id)["data"], {"value": entity})
            with reopened.connection() as db:
                self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_failed_transaction_does_not_destroy_completed_outcome(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            id = store.put("checkpoint", task_id="t", data={"next": "notify"}, status="complete")
            with self.assertRaises(RuntimeError):
                with store.connection() as db:
                    db.execute("DELETE FROM checkpoint")
                    raise RuntimeError("crash")
            self.assertEqual(store.get("checkpoint", id)["data"]["next"], "notify")
