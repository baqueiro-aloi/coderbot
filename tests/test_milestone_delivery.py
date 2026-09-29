"""Progress image delivery and announcement deduplication."""
import base64
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import config
import milestones

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main


class MilestoneDelivery(unittest.TestCase):
    def test_announcement_is_recorded_and_survives_state_roundtrip(self):
        state = {"state": "PROPOSING", "item": "task", "slug": "task"}
        with patch.object(main, "save_state") as persist, \
             patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", return_value="thread") as send:
            main.announce_milestone(state, "proposing", "Working on the proposal")
            main.announce_milestone(state, "proposing", "Working on the proposal")
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["progress"], milestones.image("proposing"))
        self.assertIn("Stage: Proposal", send.call_args.args[1])
        self.assertEqual(state["milestones_announced"], ["proposing"])
        self.assertEqual(state["thread_id"], "thread")
        persist.assert_called_once_with(state)
        self.assertIn("milestones_announced", main.RESET_KEYS)

    def test_restart_and_hold_resume_do_not_reannounce_same_stage(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(config, "STATE_PATH", Path(temp) / "state.json"), \
             patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", return_value="thread") as send:
            state = {"state": "PROPOSING", "item": "task", "slug": "task",
                     "branch": "bot-task"}
            main.announce_milestone(state, "proposing", "Writing the proposal")
            reloaded = main.load_state()
            main.announce_milestone(reloaded, "proposing", "Writing the proposal")
            self.assertEqual(send.call_count, 1)
            saved_holds = []
            with patch.object(main, "_commit_pending_work", return_value=[]), \
                 patch.object(main.task_source, "hold_task", return_value=True), \
                 patch.object(main, "_load_holds", return_value=[]), \
                 patch.object(main, "_save_holds", side_effect=lambda holds: saved_holds.extend(holds)), \
                 patch.object(main, "_reset_to_base_branch", return_value=[]), \
                 patch.object(main, "email"):
                main._hold_task(reloaded, "thread")
            self.assertEqual(saved_holds[0]["saved"]["milestones_announced"], ["proposing"])
            with patch.object(main.task_source, "unhold_task"), \
                 patch.object(main.task_source, "claim_task", return_value=True), \
                 patch.object(main, "git"), patch.object(main, "_load_holds", return_value=saved_holds), \
                 patch.object(main, "_save_holds"), patch.object(main, "email"):
                main._resume_held_task(reloaded, saved_holds[0])
            self.assertEqual(reloaded["milestones_announced"], ["proposing"])

    def test_email_progress_is_inline_and_plain_text_stays_readable(self):
        with patch.dict(sys.modules, {"googleapiclient": MagicMock(),
                                      "googleapiclient.discovery": MagicMock(),
                                      "google_auth": MagicMock()}):
            import gmail_client
        service = MagicMock()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
            "id": "message", "threadId": "thread"}
        with patch.object(gmail_client, "_gmail", return_value=service), \
             patch.object(config, "USER_EMAIL", "user@example.com"):
            gmail_client.send("stage", "Stage: Proposal", progress=milestones.image("proposing"))
        raw = service.users.return_value.messages.return_value.send.call_args.kwargs["body"]["raw"]
        from email.parser import BytesParser
        from email.policy import default
        msg = BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw))
        plain_part = msg.get_body(preferencelist=("plain",))
        html_part = msg.get_body(preferencelist=("html",))
        self.assertIsNotNone(plain_part)
        self.assertIsNotNone(html_part)
        assert plain_part is not None and html_part is not None
        self.assertIn("Stage: Proposal", plain_part.get_content())
        html = html_part.get_content()
        self.assertIn("cid:codebot-progress", html)
        related = [p for p in msg.walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["Content-ID"], "<codebot-progress>")

    def test_slack_upload_failure_keeps_text_and_thread(self):
        import slack_client
        api = MagicMock()
        api.files_upload_v2.side_effect = RuntimeError("upload failed")
        with patch.object(slack_client, "web", return_value=api), \
             patch.object(slack_client, "_to_mrkdwn", side_effect=lambda text: text):
            self.assertEqual(slack_client.send("", "Stage: Proposal", "C1:1.0",
                                               progress=milestones.image("proposing")), "C1:1.0")
        self.assertEqual(api.chat_postMessage.call_args_list[0].kwargs["thread_ts"], "1.0")
        self.assertIn("Stage: Proposal", api.chat_postMessage.call_args_list[0].kwargs["text"])
        self.assertEqual(api.files_upload_v2.call_args.kwargs["thread_ts"], "1.0")

    def test_slack_index_marks_only_successfully_delivered_evidence(self):
        import slack_client
        api = MagicMock()
        api.files_upload_v2.side_effect = RuntimeError("upload failed")
        body = "Evidence:\n- Supporting evidence: attached example.txt"
        with patch.object(slack_client, "web", return_value=api), \
             patch.object(slack_client, "_to_mrkdwn", side_effect=lambda text: text):
            slack_client.send("", body, "C1:1.0", attachments=[milestones.image("proposing")
                              .with_name("example.txt")])
        sent = api.chat_postMessage.call_args.kwargs["text"]
        self.assertIn("Evidence file unavailable", sent)
        self.assertNotIn("attached example.txt", sent)

    def test_regular_and_question_continuation_announce_proposal_once(self):
        state = {"state": "EXPLORING", "slug": "task", "branch": "bot-task", "item": "task",
                 "session_id": "sid"}
        result = SimpleNamespace(session_id="sid", output="done", question=None)
        with patch.object(main.agent_runner, "run", return_value=result), \
             patch.object(main, "handle_result", return_value=False), \
             patch.object(main, "_undo_premature_work", return_value=""), \
             patch.object(main, "save_state"), patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", return_value="thread") as send:
            main.do_explore(state)
            main._continue_exploring(state, result)
        self.assertEqual(state["state"], "PROPOSING")
        self.assertEqual(send.call_count, 1)
        self.assertEqual(state["milestones_announced"], ["proposing"])

    def test_only_confirmed_merge_gets_the_merge_diagram(self):
        for merged in (False, True):
            state = {"state": "WAIT_MERGE", "item": "task", "slug": "task"}
            with self.subTest(merged=merged), \
                 patch.object(main.task_source, "mark_done", return_value=True), \
                 patch.object(main, "email") as send:
                main._finish_task(state, "Finished", reset_repo=False, merged=merged)
            self.assertEqual(send.call_args.kwargs.get("milestone"),
                             "merged" if merged else None)
