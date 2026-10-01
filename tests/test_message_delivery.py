from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from execution_store import ExecutionStore
import message_delivery
import slack_client
import gmail_client


class DeliveryTests(unittest.TestCase):
    def test_slack_partial_delivery_retries_only_failed_file_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            paths = [Path(root) / name for name in ("one.txt", "two.txt")]
            for index, path in enumerate(paths):
                path.write_text(str(index))
            store = ExecutionStore(Path(root) / "db")
            web = Mock()
            web.files_upload_v2.side_effect = [{"files": [{"id": "F1"}]}, RuntimeError("offline")]
            web.chat_postMessage.return_value = {"ts": "1"}
            with patch.object(slack_client, "web", return_value=web):
                result = message_delivery.deliver(store, {"item": "task"}, root, root,
                    slack_client, "Error", "Short body", "C:1", paths)
                self.assertFalse(result["complete"])
                web.files_upload_v2.side_effect = None
                web.files_upload_v2.return_value = {"files": [{"id": "F2"}]}
                message_delivery.retry_pending(ExecutionStore(Path(root) / "db"),
                                                {"item": "task"}, root, slack_client)
            self.assertEqual(web.files_upload_v2.call_count, 3)
            self.assertEqual(web.chat_postMessage.call_count, 1)

    def test_email_file_failure_does_not_repeat_body(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "diagnostic.txt"
            path.write_text("trace")
            store = ExecutionStore(Path(root) / "db")
            with patch.object(gmail_client, "send", side_effect=["thread", RuntimeError("offline")]) as send:
                result = message_delivery.deliver(store, {"item": "task"}, root, root,
                    gmail_client, "Error", "Short body", None, [path])
                self.assertFalse(result["complete"])
            with patch.object(gmail_client, "send", return_value="thread") as retry:
                message_delivery.retry_pending(store, {"item": "task"}, root, gmail_client)
                self.assertEqual(retry.call_count, 1)
                self.assertEqual(retry.call_args.args[3], [path])

    def test_gmail_reconciles_acceptance_after_restart(self):
        service = Mock()
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "accepted", "threadId": "thread"}]}
        with patch.object(gmail_client, "_gmail", return_value=service):
            receipt = gmail_client.reconcile_delivery({"id": "notification"}, "file", {"status": "uncertain"})
        self.assertEqual(receipt["status"], "confirmed")

    def test_actual_email_mime_contains_complete_diagnostic(self):
        import base64
        from email.parser import BytesParser
        from email.policy import default
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "diagnostic.txt"
            path.write_text("Full traceback\n" + "frame\n" * 1000)
            service = Mock()
            service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
                "id": "sent", "threadId": "thread"}
            with patch.object(gmail_client, "_gmail", return_value=service):
                gmail_client.send("Incident", "Short summary", attachments=[path], delivery_id="stable")
            raw = service.users.return_value.messages.return_value.send.call_args.kwargs["body"]["raw"]
            message = BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw))
            file = next(message.iter_attachments())
            self.assertEqual(file.get_payload(decode=True), path.read_bytes())
            self.assertEqual(message["Message-ID"], "<stable@coderbot.local>")

    def test_pending_attachment_content_cannot_be_silently_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "report.txt"
            path.write_text("original")
            store = ExecutionStore(Path(root) / "db")
            with patch.object(gmail_client, "send", side_effect=["thread", RuntimeError("upload rejected")]):
                message_delivery.deliver(store, {"item": "task"}, root, root, gmail_client,
                                         "Incident", "Summary", None, [path])
            path.write_text("different")
            with self.assertRaisesRegex(ValueError, "content changed"):
                message_delivery.retry_pending(store, {"item": "task"}, root, gmail_client)
