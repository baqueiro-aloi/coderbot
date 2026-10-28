from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from execution_store import ExecutionStore
import message_delivery
import slack_client
import gmail_client
import diagnostics
import milestones


class DeliveryTests(unittest.TestCase):
    def test_ambiguous_slack_sdk_errors_require_reconciliation_not_reposting(self):
        from slack_sdk.errors import SlackApiError, SlackRequestError
        for error in (SlackRequestError("Lost response"),
                      SlackApiError("Server failure", {"error": "internal_error"}),
                      SlackApiError("Server failure", {"error": "fatal_error"})):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(slack_client._progress_failure_status(error), "uncertain")
        self.assertEqual(slack_client._progress_failure_status(
            SlackApiError("Denied", {"error": "invalid_auth"})), "failed")

    def test_slack_progress_is_paired_with_body_and_not_reposted_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"execution_task_id": "task"}
            web = Mock()
            web.files_upload_v2.return_value = {"files": [{"id": "F-progress"}]}
            with patch.object(slack_client, "web", return_value=web):
                result = message_delivery.deliver(store, state, root, root, slack_client,
                    "Implementation", "Review reported 2 issues; I'm fixing them.", "C:1",
                    progress=milestones.image("implementing"))
                message_delivery.retry_pending(ExecutionStore(Path(root) / "db"), state, root, slack_client)
            self.assertTrue(result["complete"])
            web.files_upload_v2.assert_called_once()
            self.assertIn("2 issues", web.files_upload_v2.call_args.kwargs["initial_comment"])
            web.chat_postMessage.assert_not_called()
            self.assertEqual(len(result["receipts"]), 2)

    def test_email_progress_is_inline_in_the_same_body_message(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            with patch.object(gmail_client, "send", return_value="thread") as send:
                result = message_delivery.deliver(store, {"execution_task_id": "task"}, root, root, gmail_client,
                    "Implementation", "Review reported 2 issues; I'm fixing them.", "thread",
                    progress=milestones.image("implementing"))
            self.assertTrue(result["complete"])
            send.assert_called_once()
            self.assertIn("2 issues", send.call_args.args[1])
            self.assertEqual(send.call_args.kwargs["progress"], milestones.image("implementing"))

    def test_uncertain_slack_pair_reconciles_exact_image_and_comment_without_resending(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"execution_task_id": "task"}
            web = Mock()
            web.files_upload_v2.side_effect = ConnectionError("connection lost after acceptance")
            with patch.object(slack_client, "web", return_value=web):
                result = message_delivery.deliver(store, state, root, root, slack_client,
                    "Implementation", "Review reported 2 issues; I'm fixing them.", "C:1",
                    progress=milestones.image("implementing"))
                self.assertFalse(result["complete"])
                envelope = store.get("delivery_receipt", result["notification_id"])["data"]["envelope"]
                progress = envelope["attachments"][0]
                web.conversations_replies.return_value = {"messages": [{"text": envelope["body"], "files": [
                    {"id": "F-paired", "name": slack_client._progress_name(envelope, progress), "size": progress["size"]}]}]}
                message_delivery.retry_pending(store, state, root, slack_client)
            self.assertEqual(store.get("delivery_receipt", result["notification_id"])["status"], "complete")
            web.files_upload_v2.assert_called_once()
            web.chat_postMessage.assert_not_called()

    def test_old_stage_image_cannot_confirm_a_new_transition_notice(self):
        import attachments
        progress = attachments.describe(milestones.image("implementing"), role="progress")
        envelope = {"id": "new-notice", "body": "Review reported 2 issues; I'm fixing them.",
                    "thread_id": "C:1", "attachments": [progress]}
        web = Mock()
        for name, text in ((progress["filename"], envelope["body"]),
                           (slack_client._progress_name(envelope, progress), "Different transition reason")):
            with self.subTest(name=name, text=text):
                web.conversations_replies.return_value = {"messages": [{"text": text, "files": [
                    {"id": "F-old", "name": name, "size": progress["size"]}]}]}
                with patch.object(slack_client, "web", return_value=web):
                    self.assertIsNone(slack_client.reconcile_delivery(envelope, "body", {"status": "uncertain"}))

    def test_paired_notice_keeps_failed_supporting_files_truthful_and_retries_only_the_file(self):
        for backend in (slack_client, gmail_client):
            with self.subTest(channel=backend.__name__), tempfile.TemporaryDirectory() as root:
                store = ExecutionStore(Path(root) / "db")
                state = {"execution_task_id": "task"}
                path = Path(root) / "diagnostic.txt"
                path.write_text("details")
                body = "Checking the changes.\nSupporting evidence: attached diagnostic.txt"
                web = Mock()
                web.files_upload_v2.side_effect = [RuntimeError("offline"), {"files": [{"id": "F-progress"}]}]
                with patch.object(slack_client, "web", return_value=web), \
                     patch.object(gmail_client, "send", side_effect=["thread", RuntimeError("offline")]) as send:
                    outcome = message_delivery.deliver(store, state, root, root, backend, "Verification", body,
                        "C:1", [path], progress=milestones.image("verifying"))
                self.assertFalse(outcome["complete"])
                if backend is slack_client:
                    notice = web.files_upload_v2.call_args.kwargs["initial_comment"]
                    self.assertIn("pending delivery (diagnostic.txt)", notice)
                    web.chat_postMessage.assert_not_called()
                else:
                    self.assertIn("delivery queued (diagnostic.txt)", send.call_args_list[0].args[1])
                    self.assertIn("progress", send.call_args_list[0].kwargs)
                web.files_upload_v2.side_effect = None
                web.files_upload_v2.return_value = {"files": [{"id": "F-file"}]}
                with patch.object(slack_client, "web", return_value=web), \
                     patch.object(gmail_client, "send", return_value="thread") as retry:
                    message_delivery.retry_pending(ExecutionStore(Path(root) / "db"), state, root, backend)
                row = store.get("delivery_receipt", outcome["notification_id"])
                self.assertEqual(row["status"], "complete")
                if backend is slack_client:
                    self.assertEqual(web.files_upload_v2.call_count, 3)
                    self.assertNotIn("initial_comment", web.files_upload_v2.call_args.kwargs)
                else:
                    retry.assert_called_once()
                    self.assertNotIn("progress", retry.call_args.kwargs)

    def test_paired_receipt_survives_interruption_between_local_confirmations(self):
        for backend in (slack_client, gmail_client):
            with self.subTest(channel=backend.__name__), tempfile.TemporaryDirectory() as root:
                store = ExecutionStore(Path(root) / "db")
                state = {"execution_task_id": "task"}
                web = Mock()
                web.files_upload_v2.return_value = {"files": [{"id": "F-progress"}]}
                with patch.object(slack_client, "web", return_value=web), \
                     patch.object(gmail_client, "send", return_value="thread") as send:
                    outcome = message_delivery.deliver(store, state, root, root, backend,
                        "Verification", "Checking changes", "C:1", progress=milestones.image("verifying"))
                    row = store.get("delivery_receipt", outcome["notification_id"])
                    for surviving in ("body", row["data"]["envelope"]["attachments"][0]["id"]):
                        store.update("delivery_receipt", row, status="pending",
                                     receipts={surviving: outcome["receipts"][surviving]})
                        message_delivery.retry_pending(ExecutionStore(Path(root) / "db"), state, root, backend)
                        self.assertEqual(store.get("delivery_receipt", row["id"])["status"], "complete")
                if backend is slack_client:
                    web.files_upload_v2.assert_called_once()
                    web.chat_postMessage.assert_not_called()
                else:
                    send.assert_called_once()

    def test_local_receipt_write_failure_does_not_relabel_an_accepted_pair(self):
        import attachments
        progress = attachments.describe(milestones.image("verifying"), role="progress")
        envelope = {"id": "notice", "thread_id": "C:1", "subject": "Verification",
                    "body": "Checking changes", "attachments": [progress]}
        for backend in (slack_client, gmail_client):
            with self.subTest(channel=backend.__name__):
                receipts = {}
                fail_write = True
                def confirm(key, value):
                    nonlocal fail_write
                    receipts[key] = value
                    if key == progress["id"] and value["status"] == "confirmed" and fail_write:
                        fail_write = False
                        raise RuntimeError("receipt write interrupted")
                web = Mock()
                web.files_upload_v2.return_value = {"files": [{"id": "accepted"}]}
                with patch.object(slack_client, "web", return_value=web), \
                     patch.object(gmail_client, "send", return_value="thread") as send:
                    with self.assertRaisesRegex(RuntimeError, "receipt write interrupted"):
                        backend.send_envelope(envelope, receipts, confirm)
                    self.assertEqual(receipts[progress["id"]]["status"], "confirmed")
                    self.assertEqual(receipts["body"]["status"], "uncertain")
                    backend.send_envelope(envelope, receipts, confirm)
                    self.assertEqual(receipts["body"]["status"], "confirmed")
                if backend is slack_client:
                    web.files_upload_v2.assert_called_once()
                else:
                    send.assert_called_once()

    def test_uncertain_email_pair_reconciles_one_message_for_text_and_image(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"execution_task_id": "task"}
            with patch.object(gmail_client, "send", side_effect=ConnectionError("accepted but disconnected")):
                outcome = message_delivery.deliver(store, state, root, root, gmail_client,
                    "Verification", "Checking changes", "thread", progress=milestones.image("verifying"))
            service = Mock()
            service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
                "messages": [{"id": "accepted", "threadId": "thread"}]}
            with patch.object(gmail_client, "_gmail", return_value=service), \
                 patch.object(gmail_client, "send") as retry:
                message_delivery.retry_pending(ExecutionStore(Path(root) / "db"), state, root, gmail_client)
            retry.assert_not_called()
            self.assertEqual(store.get("delivery_receipt", outcome["notification_id"])["status"], "complete")
            queries = service.users.return_value.messages.return_value.list.call_args_list
            self.assertEqual(len(queries), 2)
            self.assertEqual(queries[0].kwargs["q"], queries[1].kwargs["q"])

    def test_unrouted_confirmed_effect_is_not_redirected_or_sent_again(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"execution_task_id": "task"}
            old = store.record("delivery_receipt", state, root, "event", {
                "envelope": {"id": "stable", "thread_id": None, "subject": "alert", "body": "stalled", "attachments": []},
                "receipts": {"body": {"status": "confirmed", "provider_ids": ["accepted"]}}, "channel": "slack_client"})
            with patch.object(slack_client, "send_envelope") as sender:
                with self.assertRaisesRegex(ValueError, "confirmed or uncertain"):
                    message_delivery.deliver(store, state, root, root, slack_client, "alert", "stalled", "C:1", identity="event")
            sender.assert_not_called()
            self.assertEqual(store.get("delivery_receipt", old["id"])["data"], old["data"])

    def test_generated_markdown_diagnostic_delivery_in_both_channels(self):
        for backend in (slack_client, gmail_client):
            with self.subTest(channel=backend.__name__), tempfile.TemporaryDirectory() as root:
                store = ExecutionStore(Path(root) / "db")
                path = diagnostics.report(store, {"item": "task"}, root, root, "VERIFYING", detail="Full details")
                def send(envelope, receipts, confirm):
                    artifact = envelope["attachments"][0]
                    self.assertEqual(artifact["filename"], path.name)
                    self.assertEqual(artifact["media_type"], "text/markdown")
                    self.assertEqual(artifact["role"], "diagnostic")
                    self.assertEqual(Path(artifact["path"]).read_bytes(), path.read_bytes())
                    confirm("body", {"status": "confirmed"})
                    confirm(artifact["id"], {"status": "confirmed"})
                    return "thread"
                with patch.object(backend, "send_envelope", side_effect=send):
                    result = message_delivery.deliver(store, {"item": "task"}, root, root,
                        backend, "Results", "Supporting details: " + path.name, "C:1", [path])
                self.assertTrue(result["complete"])

    def test_empty_slack_attachment_is_delivered_as_explicit_empty_output_not_pass(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "green-eslint.txt"
            path.write_bytes(b"")
            store = ExecutionStore(Path(root) / "db")
            web = Mock()
            web.files_upload_v2.return_value = {"files": [{"id": "F1"}]}
            web.chat_postMessage.return_value = {"ts": "1"}
            with patch.object(slack_client, "web", return_value=web):
                outcome = message_delivery.deliver(store, {"item": "task"}, root, root,
                    slack_client, "Reply", "Lint diagnosis", "C:1", [path])
            self.assertTrue(outcome["complete"])
            upload = web.files_upload_v2.call_args.kwargs
            self.assertNotIn("file", upload)
            self.assertIn("0 bytes", upload["content"])
            self.assertIn("does not establish a check result", upload["content"])
            self.assertEqual(path.read_bytes(), b"")

    def test_provider_exception_keeps_notification_pending_with_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            backend = Mock(__name__="fixture")
            backend.attachment_limits.return_value = {"file": 10000, "mime": False}
            backend.send_envelope.side_effect = ConnectionError("Slack unavailable")
            result = message_delivery.deliver(store, {"item": "task"}, root, root,
                                             backend, "Reply", "Completed answer", "C:1")
            self.assertFalse(result["complete"])
            row = store.get("delivery_receipt", result["notification_id"])
            self.assertEqual(row["status"], "pending")
            self.assertIn("Slack unavailable", row["data"]["last_error"])

    def test_log_delivery_uses_txt_name_and_preserves_contents_in_both_channels(self):
        for backend in (slack_client, gmail_client):
            with self.subTest(channel=backend.__name__), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "baseline.log"
                path.write_text("Resultado completo\n")
                store = ExecutionStore(Path(root) / "db")
                def send(envelope, receipts, confirm):
                    artifact = envelope["attachments"][0]
                    self.assertEqual(artifact["filename"], "baseline.txt")
                    self.assertEqual(artifact["media_type"], "text/plain")
                    self.assertEqual(Path(artifact["path"]).read_bytes(), path.read_bytes())
                    self.assertIn("baseline.txt", envelope["body"])
                    confirm("body", {"status": "confirmed"})
                    confirm(artifact["id"], {"status": "confirmed"})
                    return "thread"
                with patch.object(backend, "send_envelope", side_effect=send):
                    result = message_delivery.deliver(store, {"item": "task"}, root, root,
                        backend, "Results", "Evidence: attached baseline.log", "C:1", [path])
                self.assertTrue(result["complete"])
                self.assertTrue(path.is_file())

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
            path = diagnostics.report(ExecutionStore(Path(root) / "db"), {"item": "task"},
                root, root, "VERIFYING", detail="Full traceback\n" + "frame\n" * 1000)
            service = Mock()
            service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
                "id": "sent", "threadId": "thread"}
            with patch.object(gmail_client, "_gmail", return_value=service):
                gmail_client.send("Incident", "Short summary", attachments=[path], delivery_id="stable")
            raw = service.users.return_value.messages.return_value.send.call_args.kwargs["body"]["raw"]
            message = BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw))
            file = next(message.iter_attachments())
            self.assertEqual(file.get_payload(decode=True), path.read_bytes())
            self.assertEqual(file.get_filename(), path.name)
            self.assertEqual(file.get_content_type(), "text/markdown")
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
