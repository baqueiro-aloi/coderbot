"""Owned Slack threads and durable Socket Mode events, without a workspace."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import config
import slack_client as slack


class SlackInbox(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for name, value in (("DATA_DIR", Path(self.dir.name)),
                            ("SLACK_CHANNEL_ID", "C123")):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(slack, "_bot_user", "Ubot")
        p.start()
        self.addCleanup(p.stop)
        self.web = MagicMock()
        self.web.chat_postMessage.return_value = {"ts": "100.000001"}
        self.web.conversations_history.return_value = {"messages": []}
        p = patch.object(slack, "web", return_value=self.web)
        p.start()
        self.addCleanup(p.stop)
        with slack._database() as db:
            db.execute("INSERT INTO roots(channel,root_ts,nonce) VALUES(?,?,?)",
                       ("C123", "100.000001", "nonce"))

    def event(self, ts, text, root="100.000001", channel="C123", user="Uhuman"):
        return {"event": {"type": "message", "ts": ts, "thread_ts": root,
                          "channel": channel, "user": user, "text": text}}

    def test_owned_thread_only_and_deduplicated_across_database_reopens(self):
        self.assertFalse(slack._accept_event(self.event("101.000001", "ABORT", root="100.000002")))
        self.assertFalse(slack._accept_event(self.event("101.000001", "ABORT", channel="COTHER")))
        self.assertFalse(slack._accept_event(self.event("101.000001", "ABORT", user="Ubot")))
        self.assertFalse(slack._accept_event(self.event("101.000001", "ABORT", root="101.000001")))
        self.assertTrue(slack._accept_event(self.event("102.000002", "second")))
        self.assertTrue(slack._accept_event(self.event("101.000001", "STATUS")))
        self.assertTrue(slack._accept_event(self.event("101.000001", "STATUS")))
        self.assertEqual(slack.poll_command()[:3], ("C123:101.000001", "C123:100.000001", "STATUS"))
        self.assertEqual(slack.poll_reply("C123:100.000001"), ("C123:101.000001", "STATUS"))
        slack.mark_processed("C123:101.000001")
        self.assertEqual(slack.poll_reply("C123:100.000001"), ("C123:102.000002", "second"))
        self.assertEqual(slack.drain_thread("C123:100.000001"), 1)
        self.assertIsNone(slack.poll_reply("C123:100.000001"))

    def test_socket_ack_after_persistence_and_retry_on_database_failure(self):
        socket = MagicMock()
        request = SimpleNamespace(type="events_api", envelope_id="E1",
                                  payload=self.event("101.000001", "hello"))
        with patch.dict("sys.modules", {
                "slack_sdk.socket_mode.response": SimpleNamespace(SocketModeResponse=lambda **kw: kw)}):
            slack._socket_request(socket, request)
            self.assertEqual(slack.poll_reply("C123:100.000001")[1], "hello")
            socket.send_socket_mode_response.assert_called_once_with({"envelope_id": "E1"})
            socket.reset_mock()
            with patch.object(slack, "_accept_event", side_effect=OSError("disk full")):
                slack._socket_request(socket, request)
            socket.send_socket_mode_response.assert_not_called()

    def test_existing_root_is_reused_and_task_messages_stay_threaded(self):
        state = {"item": "task", "thread_nonce": "nonce"}
        self.assertEqual(slack.open_thread(state), "C123:100.000001")
        self.web.chat_postMessage.assert_not_called()
        body = "X" * 3800 + "\n" + "Y" * 4300
        self.assertEqual(slack.send("ignored", body, "C123:100.000001"), "C123:100.000001")
        self.assertEqual("".join(c.kwargs["text"] for c in self.web.chat_postMessage.call_args_list), body)
        self.assertTrue(all(c.kwargs["thread_ts"] == "100.000001"
                            for c in self.web.chat_postMessage.call_args_list))
        slack.close_thread("C123:100.000001")
        self.assertFalse(slack._accept_event(self.event("103.000001", "later")))

    def test_uncertain_root_post_is_reconciled_from_channel_history(self):
        with slack._database() as db:
            db.execute("DELETE FROM roots")
        self.web.conversations_history.return_value = {"messages": [{
            "user": "Ubot", "ts": "77.123456", "text": "Task [codebot-task:recover-me]"}]}
        thread = slack.open_thread({"item": "task", "thread_nonce": "recover-me"})
        self.assertEqual(thread, "C123:77.123456")
        self.web.chat_postMessage.assert_not_called()
        self.assertEqual(slack.open_thread({"item": "task", "thread_nonce": "recover-me"}),
                         thread)

    def test_new_root_contains_task_identity_and_is_registered(self):
        with slack._database() as db:
            db.execute("DELETE FROM roots")
        thread = slack.open_thread({"item": "Fix checkout", "item_url": "https://jira.test/123",
                                    "thread_nonce": "new-nonce"})
        self.assertEqual(thread, "C123:100.000001")
        text = self.web.chat_postMessage.call_args.kwargs["text"]
        self.assertIn(config.INSTANCE_ID, text)
        self.assertIn("Fix checkout", text)
        self.assertIn("https://jira.test/123", text)
        self.assertIn("[codebot-task:new-nonce]", text)
        self.assertEqual(slack.open_thread({"thread_nonce": "new-nonce"}), thread)
        self.web.chat_postMessage.assert_called_once()

    def test_actual_socket_sdk_exposes_receiver_contract(self):
        try:
            from slack_sdk.socket_mode import SocketModeClient
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError:
            self.skipTest("slack-sdk is installed in the application environment")
        self.assertTrue(callable(SocketModeClient))
        self.assertEqual(SocketModeResponse(envelope_id="E1").envelope_id, "E1")

    def test_start_uses_individual_app_token_and_registers_socket_handler(self):
        try:
            from slack_sdk.socket_mode import SocketModeClient
        except ImportError:
            self.skipTest("slack-sdk is installed in the application environment")
        with patch.object(config, "SLACK_APP_TOKEN", "xapp-this-instance"), \
             patch.object(slack, "_socket", None), \
             patch.object(slack, "validate") as validate, \
             patch("slack_sdk.socket_mode.SocketModeClient") as socket:
            slack.start()
        validate.assert_called_once()
        self.assertEqual(socket.call_args.kwargs["app_token"], "xapp-this-instance")
        self.assertIn(slack._socket_request,
                      socket.return_value.socket_mode_request_listeners.append.call_args.args)
        socket.return_value.connect.assert_called_once()

    def test_receiver_enqueues_while_agent_turn_is_busy_and_wakes_next_tick(self):
        agent_running = threading.Event()
        release_agent = threading.Event()
        finished = threading.Event()

        def agent_turn():
            agent_running.set()
            release_agent.wait(2)
            finished.set()

        worker = threading.Thread(target=agent_turn)
        worker.start()
        try:
            self.assertTrue(agent_running.wait(2))
            self.assertTrue(slack._accept_event(self.event("101.000001", "approve")))
            self.assertFalse(finished.is_set())  # event intake did not interrupt the turn
            release_agent.set()
            worker.join(timeout=2)
            self.assertTrue(finished.is_set())
            self.assertEqual(slack.poll_reply("C123:100.000001"),
                             ("C123:101.000001", "approve"))
            slack.wait(0.01)
            self.assertFalse(slack._wake.is_set())
        finally:
            release_agent.set()
            worker.join(timeout=2)

    def test_validate_requires_public_member_channel(self):
        self.web.auth_test.return_value = {"user_id": "Ubot"}
        self.web.conversations_info.return_value = {"channel": {"is_private": False,
                                                                   "is_channel": True,
                                                                   "is_member": True}}
        slack.validate()
        self.web.conversations_info.return_value = {"channel": {"is_private": True,
                                                                   "is_channel": False}}
        with self.assertRaisesRegex(RuntimeError, "public"):
            slack.validate()

    def test_validate_rejects_missing_bot_scopes_when_reported(self):
        class AuthResponse(dict):
            headers = {"x-oauth-scopes": "chat:write,channels:read"}
        self.web.auth_test.return_value = AuthResponse(user_id="Ubot")
        with self.assertRaisesRegex(RuntimeError, "channels:history.*files:write"):
            slack.validate()

    def test_uploads_small_evidence_in_thread_and_reports_upload_failure(self):
        path = Path(self.dir.name) / "report.html"
        path.write_text("report")
        self.web.files_upload_v2.side_effect = RuntimeError("upload denied")
        slack.send("PR ready", "Review the PR", "C123:100.000001", [path])
        self.web.files_upload_v2.assert_called_once_with(
            channel="C123", thread_ts="100.000001", file=str(path), filename="report.html")
        self.assertIn("Evidence file unavailable: report.html",
                      [call.kwargs["text"] for call in self.web.chat_postMessage.call_args_list])

    def test_unhandled_stale_replies_are_drained_before_new_merge_decision(self):
        self.assertTrue(slack._accept_event(self.event("101.000001", "merge")))
        self.assertTrue(slack._accept_event(self.event("102.000001", "feedback")))
        self.assertEqual(slack.drain_thread("C123:100.000001"), 2)
        self.assertIsNone(slack.poll_reply("C123:100.000001"))
        self.assertTrue(slack._accept_event(self.event("103.000001", "merge")))
        self.assertEqual(slack.poll_reply("C123:100.000001"),
                         ("C123:103.000001", "merge"))


if __name__ == "__main__":
    unittest.main()
