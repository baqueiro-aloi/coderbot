"""Independent conversation selection retains Gmail's existing call contract."""
import sys
import unittest
from unittest.mock import MagicMock, patch

import config
import conversation
import task_source


class Dispatch(unittest.TestCase):
    def test_email_calls_existing_client_unchanged(self):
        gmail = MagicMock()
        gmail.send.return_value = "gmail-thread"
        with patch.object(config, "COMM_CHANNEL", "email"), \
             patch.dict(sys.modules, {"gmail_client": gmail}):
            self.assertIsNone(conversation.open_thread({"item": "task"}))
            self.assertEqual(conversation.send("subject", "body", "prior", []), "gmail-thread")
            gmail.send.assert_called_once_with("subject", "body", "prior", [])
            conversation.poll_reply("gmail-thread")
            gmail.poll_reply.assert_called_once_with("gmail-thread")

    def test_slack_calls_only_slack_adapter(self):
        slack = MagicMock()
        slack.open_thread.return_value = "C123:1.1"
        slack.send.return_value = "C123:1.1"
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.dict(sys.modules, {"slack_client": slack}):
            self.assertEqual(conversation.open_thread({"item": "task"}), "C123:1.1")
            self.assertEqual(conversation.send("subject", "body", "C123:1.1"), "C123:1.1")
            conversation.start()
            slack.start.assert_called_once()

    def test_jira_and_slack_do_not_require_gmail_import_or_email_address(self):
        slack = MagicMock()
        slack.send.return_value = "C123:1.1"
        jira = MagicMock()
        jira.list_pending_items.return_value = [{"id": "100", "text": "task"}]
        with patch.multiple(config, COMM_CHANNEL="slack", TASK_SOURCE="jira", USER_EMAIL=""), \
             patch.dict(sys.modules, {"slack_client": slack, "jira_client": jira,
                                      "gmail_client": None}):
            self.assertEqual(task_source.list_pending_items()[0]["id"], "100")
            self.assertEqual(conversation.send("x", "hello", "C123:1.1"), "C123:1.1")
            self.assertIsNone(conversation.foreign_command("STATUS"))


if __name__ == "__main__":
    unittest.main()
