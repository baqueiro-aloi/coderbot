import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import evidence_delivery
import feedback
from execution_store import ExecutionStore


class EvidenceDeliveryTests(unittest.TestCase):
    def test_mixed_delivery_waits_for_product_completion_and_review(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"item": "task", "state": "IMPLEMENTING"}
            product = feedback.receive(store, state, root, "product", "Change UI and upload demo")
            delivery = feedback.receive(store, state, root, "delivery", "Upload demo")
            store.update("feedback", delivery, after_product_feedback=product["id"])
            self.assertEqual([r["id"] for r in feedback.pending(store, state, root)], [product["id"]])
            store.update("feedback", product, status="complete")
            self.assertEqual(feedback.pending(store, state, root), [])
            state["state"] = "WAIT_MERGE"
            self.assertEqual([r["id"] for r in feedback.pending(store, state, root)], [delivery["id"]])

    def test_delivery_feedback_preserves_review_decision(self):
        import main
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"state": "WAIT_MERGE", "item": "task", "slug": "task",
                     "pr_url": "https://github.com/a/b/pull/1", "pending_decision": {"question": "Merge?"}}
            row = feedback.receive(store, state, root, "message", "Publish the demo to Drive")
            assessment = {"action": "delivery", "answer": "Publish demo", "reason": "Delivery", "references": "demo"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.agent_runner, "run", return_value=Mock(output=json.dumps(assessment))), \
                 patch.object(main.evidence_delivery, "deliver", return_value={"status": "complete"}) as deliver, \
                 patch.object(main, "email"), patch.object(main, "save_state"):
                main._apply_received_feedback(state, store, row)
            self.assertEqual(state["state"], "WAIT_MERGE")
            self.assertEqual(state["pending_decision"], {"question": "Merge?"})
            deliver.assert_called_once()
            self.assertEqual(store.get("feedback", row["id"])["status"], "complete")

    def test_investigation_passes_actual_attachments_to_sender(self):
        import main
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            outbox = Path(root) / "outbox"
            outbox.mkdir()
            report = outbox / "report.json"
            report.write_text("{}")
            state = {"state": "WAIT_MERGE", "item": "task", "slug": "task"}
            row = feedback.receive(store, state, root, "message", "Show the report")
            assessment = {"action": "answer", "answer": f"Report\nATTACH: {report}", "reason": "Existing", "references": "report"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DATA_DIR", Path(root)), \
                 patch.object(main.agent_runner, "run", return_value=Mock(output=json.dumps(assessment))), \
                 patch.object(main, "email") as notify, patch.object(main, "save_state"):
                main._apply_received_feedback(state, store, row)
            self.assertEqual(notify.call_args.args[3], [report.resolve()])
            self.assertNotIn("ATTACH:", notify.call_args.args[2])

    def test_upload_failure_resumes_without_recording_or_conversion_again(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            video = Path(root) / "demo.mp4"
            video.write_bytes(b"video")
            state = {"item": "task", "branch": "feature", "pr_url": "https://github.com/a/b/pull/1", "thread_id": "thread"}
            sync, notify = Mock(), Mock()
            with patch("evidence_delivery.snapshot", return_value="snapshot"), \
                 patch("evidence.valid_media", return_value=True), \
                 patch("evidence.record_evidence", return_value=[video]) as record, \
                 patch("drive_client.publish_evidence", side_effect=[
                     {"status": "retryable", "stage": "upload"},
                      {"status": "complete", "id": "a", "url": "https://drive.google.com/file/d/a/view"},
                      {"status": "complete", "id": "a", "access": True, "url": "https://drive.google.com/file/d/a/view"}]) as upload:
                first = evidence_delivery.deliver(store, state, root, sync_pr=sync, notify=notify)
                self.assertEqual(first["status"], "retryable")
                second = evidence_delivery.deliver(store, state, root, sync_pr=sync, notify=notify)
                self.assertEqual(second["stage"], "delivered")
                self.assertEqual(record.call_count, 1)
                self.assertEqual(upload.call_count, 3)
            sync.assert_called_once()
            notify.assert_called_once()

    def test_attachment_markers_are_actual_allowed_files(self):
        with tempfile.TemporaryDirectory() as root:
            outbox = Path(root) / "outbox"
            outbox.mkdir()
            video = outbox / "demo.webm"
            video.write_bytes(b"video")
            value = {"answer": f"Demo:\nATTACH: {video}\nATTACH: /etc/passwd"}
            with patch.object(feedback.config, "DATA_DIR", Path(root)):
                text, files = feedback.attachments(value)
            self.assertEqual(files, [video.resolve()])
            self.assertNotIn("ATTACH:", text)
            self.assertIn("outside authorized", text)

    def test_delivery_action_is_valid_and_context_explains_capabilities(self):
        value = {"action": "delivery", "answer": "Publish video", "reason": "Delivery only", "references": "demo"}
        self.assertEqual(feedback.validate(value), value)
        self.assertIn("not product scope changes", feedback.investigation({}, {"data": {"text": "Upload demo"}}))

    def test_pr_failure_keeps_upload_and_retries_only_sync(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            video = Path(root) / "demo.mp4"
            video.write_bytes(b"video")
            state = {"item": "task", "branch": "feature", "pr_url": "https://github.com/a/b/pull/1", "thread_id": "thread"}
            sync = Mock(side_effect=[RuntimeError("PR unavailable"), None])
            with patch("evidence_delivery.snapshot", return_value="snapshot"), \
                 patch("evidence.valid_media", return_value=True), \
                 patch("evidence.record_evidence", return_value=[video]) as record, \
                  patch("drive_client.publish_evidence", return_value={"status": "complete", "id": "a", "access": True,
                     "url": "https://drive.google.com/file/d/a/view"}) as upload:
                with self.assertRaisesRegex(RuntimeError, "PR unavailable"):
                    evidence_delivery.deliver(store, state, root, sync_pr=sync, notify=Mock())
                evidence_delivery.deliver(store, state, root, sync_pr=sync, notify=Mock())
                self.assertEqual(upload.call_count, 2)  # Upload and access each run once.
                self.assertEqual(record.call_count, 1)
            self.assertEqual(sync.call_count, 2)

    def test_blocked_access_does_not_update_pr_or_notify(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            video = Path(root) / "demo.mp4"
            video.write_bytes(b"video")
            state = {"item": "task", "pr_url": "https://github.com/a/b/pull/1"}
            sync, notify = Mock(), Mock()
            with patch("evidence_delivery.snapshot", return_value="snapshot"), \
                 patch("evidence.valid_media", return_value=True), \
                 patch("evidence.record_evidence", return_value=[video]), \
                  patch("drive_client.publish_evidence", side_effect=[{"status": "complete", "id": "a", "url": "url"},
                      {"status": "blocked", "stage": "access", "url": "url"}]):
                result = evidence_delivery.deliver(store, state, root, sync_pr=sync, notify=notify)
            self.assertEqual(result["status"], "blocked")
            sync.assert_not_called()
            notify.assert_not_called()

    def test_failed_conversion_preserves_recording_for_retry(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            clip, mp4 = Path(root) / "demo.webm", Path(root) / "demo.mp4"
            clip.write_bytes(b"clip")
            mp4.write_bytes(b"mp4")
            state = {"item": "task", "pr_url": "https://github.com/a/b/pull/1", "thread_id": "thread"}
            with patch("evidence_delivery.snapshot", return_value="snapshot"), \
                 patch("evidence.valid_media", side_effect=lambda p: Path(p).is_file()), \
                 patch("evidence.record_evidence", return_value=[clip]) as record, \
                 patch("evidence.stitch_playwright_clips", side_effect=[None, mp4]) as convert, \
                  patch("drive_client.publish_evidence", return_value={"status": "complete", "id": "a", "access": True, "url": "url"}):
                first = evidence_delivery.deliver(store, state, root, sync_pr=Mock(), notify=Mock())
                self.assertEqual(first["stage"], "conversion")
                self.assertTrue(clip.exists())
                second = evidence_delivery.deliver(store, state, root, sync_pr=Mock(), notify=Mock())
                self.assertEqual(second["status"], "complete")
                self.assertEqual(record.call_count, 1)
                self.assertEqual(convert.call_count, 2)
