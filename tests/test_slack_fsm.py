"""Slack thread-scoped commands cannot mutate an unrelated active task."""
import unittest
from unittest.mock import MagicMock, patch

import config
import main


class ThreadCommands(unittest.TestCase):
    def test_abort_held_task_does_not_abort_active_task(self):
        state = {"state": "WAIT_APPROVAL", "item": "active", "thread_id": "C123:2.0"}
        hold = {"thread_id": "C123:1.0", "item": "held", "item_id": "issue-1",
                "branch": "old-branch", "requested": False}
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(main, "_load_holds", return_value=[hold]), \
             patch.object(main, "_save_holds") as save_holds, \
             patch.object(main.task_source, "unhold_task", return_value=True) as unhold, \
             patch.object(main.task_source, "unclaim_task", return_value=True) as unclaim, \
             patch.object(main.gmail_client, "poll_command", return_value=(
                 "C123:3.0", "C123:1.0", "ABORT", False, "")), \
             patch.object(main.gmail_client, "send", return_value="C123:1.0") as send, \
             patch.object(main.gmail_client, "mark_processed") as processed, \
             patch.object(main.gmail_client, "close_thread") as close:
            self.assertFalse(main.check_commands(state))
        self.assertEqual(state["item"], "active")
        self.assertEqual(state["state"], "WAIT_APPROVAL")
        unhold.assert_called_once_with("held", "issue-1")
        unclaim.assert_called_once_with("held", "issue-1")
        save_holds.assert_called_once_with([])
        self.assertEqual(send.call_args.args[2], "C123:1.0")
        processed.assert_called_once_with("C123:3.0")
        close.assert_called_once_with("C123:1.0")

    def test_done_and_status_on_hold_are_scoped_to_that_hold(self):
        state = {"state": "WAIT_MERGE", "item": "active", "thread_id": "C123:2.0"}
        hold = {"thread_id": "C123:1.0", "item": "held", "item_id": "issue-1",
                "branch": "old-branch", "requested": False}
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(main, "_load_holds", return_value=[hold]), \
             patch.object(main, "_save_holds") as save_holds, \
             patch.object(main.task_source, "mark_done", return_value=True) as mark_done, \
             patch.object(main.gmail_client, "send", return_value="C123:1.0") as send, \
             patch.object(main.gmail_client, "mark_processed") as processed, \
             patch.object(main.gmail_client, "close_thread") as close:
            self.assertTrue(main._handle_held_command("msg-1", "C123:1.0", "STATUS", ""))
            send.assert_called_once()
            self.assertIn("on hold: held", send.call_args.args[1])
            mark_done.assert_not_called()
            self.assertTrue(main._handle_held_command("msg-2", "C123:1.0", "DONE", ""))
        self.assertEqual(state["item"], "active")
        mark_done.assert_called_once_with("held", "issue-1")
        save_holds.assert_called_once_with([])
        self.assertEqual(processed.call_count, 2)
        close.assert_called_once_with("C123:1.0")

    def test_continue_on_held_thread_queues_resume_without_touching_active(self):
        hold = {"thread_id": "C123:1.0", "item": "held", "item_id": "issue-1"}
        with patch.object(main, "_load_holds", return_value=[hold]), \
             patch.object(main, "_request_continue", return_value=True) as request, \
             patch.object(main.gmail_client, "send", return_value="C123:1.0"), \
             patch.object(main.gmail_client, "mark_processed") as processed:
            self.assertTrue(main._handle_held_command("msg-3", "C123:1.0", "CONTINUE", "use B"))
        request.assert_called_once_with("C123:1.0", "use B")
        processed.assert_called_once_with("msg-3")

    def test_restart_does_not_replay_checkpointed_merge_reply(self):
        state = {"state": "WAIT_MERGE", "item": "task", "thread_id": "C123:1.0",
                 "slack_last_handled_id": "C123:2.0"}
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(main.gmail_client, "poll_reply", return_value=("C123:2.0", "merge")), \
             patch.object(main.gmail_client, "mark_processed") as processed, \
             patch.object(main, "_handle_reply") as handler:
            main.handle_wait(state)
        handler.assert_not_called()
        processed.assert_called_once_with("C123:2.0")

    def test_completed_hold_command_never_targets_new_active_task(self):
        state = {"state": "WAIT_APPROVAL", "item": "new task", "thread_id": "C123:2.0"}
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(main, "_load_holds", return_value=[]), \
             patch.object(main.gmail_client, "poll_command", return_value=(
                 "C123:3.0", "C123:1.0", "ABORT", False, "")), \
             patch.object(main.gmail_client, "mark_processed") as processed, \
             patch.object(main, "_abort_and_reset") as abort:
            self.assertFalse(main.check_commands(state))
        abort.assert_not_called()
        processed.assert_called_once_with("C123:3.0")


if __name__ == "__main__":
    unittest.main()
