"""Slack pre-task cleanup is announced once and retried without accepting replies."""
import unittest
from unittest.mock import MagicMock, patch

import config
with patch.dict("sys.modules", {"gmail_client": MagicMock()}):
    import main


class WaitClean(unittest.TestCase):
    def test_dirty_check_announces_once_and_clean_check_resumes(self):
        state = {"state": "IDLE"}
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(main, "git", return_value=" M file"), \
             patch.object(main.gmail_client, "announce") as announce:
            main.do_pick(state)
            self.assertEqual(state["state"], "WAIT_CLEAN")
            main.check_clean_checkout(state)
            self.assertEqual(state["state"], "WAIT_CLEAN")
            main.do_pick(state)
            announce.assert_called_once()
            self.assertNotIn("thread_id", state)
        with patch.object(main, "git", return_value=""):
            main.check_clean_checkout(state)
        self.assertEqual(state["state"], "IDLE")
        self.assertNotIn("dirty_notified", state)


if __name__ == "__main__":
    unittest.main()
