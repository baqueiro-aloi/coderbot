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
    def test_verification_block_includes_results_and_agent_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence = Path(temp) / "playwright.log"
            evidence.write_text("2 tests passed")
            diagnostic = Path(temp) / "diagnostic.txt"
            diagnostic.write_text("Full results")
            state = {"state": "VERIFYING", "item": "task", "verify_round": 2}
            report = "14/25 tasks complete; 11 pending.\n" + "Details\n" * 200
            with patch.object(main.diagnostics, "report", return_value=diagnostic), \
                 patch.object(main, "email") as send:
                main._gate_failed(state, "VERIFYING", "verify_round", "incomplete tasks",
                                  report, [evidence])
            self.assertEqual(send.call_args.args[3], [diagnostic, evidence])
            self.assertIn("14/25 tasks", send.call_args.kwargs["visible_question"])
            self.assertIn("return to implementation", state["pending_question"])
            self.assertEqual(state["state"], "WAIT_REPLY")

    def test_long_investigation_keeps_complete_question_visible_after_wait_banner(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as temp, \
                 patch.object(config, "COMM_CHANNEL", channel), \
                 patch.object(main, "save_state"), patch.object(main, "trail"), \
                 patch.object(main, "_transcript_append"), patch.object(main, "_transcript_note"), \
                 patch.object(main.diagnostics, "report", return_value=Path(temp) / "details.txt"), \
                 patch.object(main.gmail_client, "deliver", return_value={"thread_id": "thread", "complete": True}) as deliver, \
                 patch.object(main.gmail_client, "send", return_value="thread"):
                question = "¿Aprobamos este enfoque?\n" + "- Opción y consecuencias.\n" * 110
                result = SimpleNamespace(session_id="sid", output="Investigation\n" * 100,
                    preamble="Investigation\n" * 100, question=question, attachments=[])
                state = {"state": "EXPLORING", "item": "task", "slug": "task", "thread_id": "thread"}
                self.assertTrue(main.handle_result(state, result, "EXPLORING"))
                sent_body = deliver.call_args.args[2]
                self.assertIn(question, sent_body)
                self.assertNotIn("Investigation", sent_body)
                self.assertIn("details.txt", sent_body)
                self.assertEqual(state["pending_question"], question)
                original = dict(state["last_email"])
                main._announce_state(state)
                self.assertEqual(state["last_email"], original)
                self.assertIn(question, state["last_email"]["body"])

    def test_exploration_notice_survives_restart_and_agent_failures(self):
        for channel in ("email", "slack"):
            for language in ("English", "Spanish"):
                with self.subTest(channel=channel, language=language), \
                     tempfile.TemporaryDirectory() as temp, \
                     patch.object(config, "STATE_PATH", Path(temp) / "state.json"), \
                     patch.object(config, "COMM_CHANNEL", channel), \
                     patch.object(main, "trail"), \
                     patch.object(main.gmail_client, "send", return_value="thread") as send, \
                     patch.object(main.agent_runner, "run") as run:
                    state = {"state": "EXPLORING", "item": "task", "slug": "task",
                             "branch": "bot-task", "task_language": language,
                             "thread_id": "thread"}
                    def delivered_before_agent(*args, **kwargs):
                        send.assert_called_once()
                        self.assertTrue(milestones.announced(main.load_state(), "exploring"))
                        raise ConnectionError("fetch failed")
                    run.side_effect = delivered_before_agent
                    with self.assertRaisesRegex(ConnectionError, "fetch failed"):
                        main.do_explore(state)
                    reloaded = main.load_state()
                    with self.assertRaisesRegex(ConnectionError, "fetch failed"):
                        main.do_explore(reloaded)
                    send.assert_called_once()
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(send.call_args.args[2], "thread")
                    expected = ("Estoy explorando el código del repositorio." if language == "Spanish"
                                else "I'm exploring the codebase.")
                    self.assertEqual(send.call_args.args[1], expected)
                    self.assertIn("Exploración" if language == "Spanish" else "Exploration",
                                  send.call_args.args[0])

    def test_failed_exploration_notice_is_retried_before_agent_work(self):
        state = {"state": "EXPLORING", "item": "task", "slug": "task", "branch": "bot-task"}
        with patch.object(main, "save_state"), patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", side_effect=[ConnectionError("send failed"), "thread"]) as send, \
             patch.object(main.agent_runner, "run", side_effect=ConnectionError("fetch failed")) as run:
            with self.assertRaisesRegex(ConnectionError, "send failed"):
                main.do_explore(state)
            run.assert_not_called()
            self.assertFalse(milestones.announced(state, "exploring"))
            with self.assertRaisesRegex(ConnectionError, "fetch failed"):
                main.do_explore(state)
            self.assertTrue(milestones.announced(state, "exploring"))
            self.assertEqual(send.call_count, 2)

    def test_announcement_is_recorded_and_survives_state_roundtrip(self):
        state = {"state": "PROPOSING", "item": "task", "slug": "task"}
        with patch.object(main, "save_state") as persist, \
             patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", return_value="thread") as send:
            main.announce_milestone(state, "proposing", "Working on the proposal")
            main.announce_milestone(state, "proposing", "Working on the proposal")
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["progress"], milestones.image("proposing"))
        self.assertEqual(state["banner_state"], "PROPOSING")
        self.assertTrue(persist.called)
        self.assertIn("milestones_announced", main.RESET_KEYS)

    def test_restart_and_hold_resume_do_not_reannounce_same_stage(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(config, "STATE_PATH", Path(temp) / "state.json"), \
             patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", return_value="thread") as send:
            state = {"state": "PROPOSING", "item": "task", "slug": "task",
                     "branch": "bot-task"}
            main.announce_milestone(state, "proposing", "Writing the proposal")
            main.save_state(state)
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
        self.assertEqual(send.call_count, 2)
        self.assertEqual(state["milestones_announced"], ["exploring", "proposing"])

    def test_every_state_entry_gets_banner_even_within_same_step_and_on_return(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as temp, \
                 patch.object(config, "STATE_PATH", Path(temp) / "state.json"), \
                 patch.object(config, "COMM_CHANNEL", channel), patch.object(main, "trail"), \
                 patch.object(main.agent_runner, "run") as run, \
                 patch.object(main.gmail_client, "send", return_value="thread") as send:
                state = {"item": "task", "slug": "task", "task_language": "Spanish",
                         "thread_id": "thread"}
                phases = ["VERIFYING", "INTERNAL_REVIEW", "E2E", "WAIT_REPLY", "E2E",
                          "ARCHIVING", "OPEN_PR", "WAIT_REVIEW", "WAIT_MERGE",
                          "ADDRESS_PR_THREADS", "WAIT_MERGE", "WAIT_STUCK", "RECOVERING",
                          "REPLANNING", "WAIT_APPROVAL", "IMPLEMENTING", "APPLY_FEEDBACK"]
                for index, phase in enumerate(phases, 1):
                    state["state"] = phase
                    main._announce_state(state)
                    self.assertEqual(send.call_count, index)
                    self.assertIn(phase, send.call_args.args[1])
                    self.assertTrue(send.call_args.kwargs["progress"].is_file())
                    state = main.load_state()
                    main._announce_state(state)
                    self.assertEqual(send.call_count, index)
                run.assert_not_called()
                state["state"] = "IDLE"
                main._announce_state(state)
                self.assertEqual(send.call_count, len(phases))

    def test_pending_banner_failure_does_not_fail_phase_and_retries(self):
        state = {"state": "E2E", "item": "task", "slug": "task"}
        with patch.object(main, "save_state"), patch.object(main, "trail"), \
             patch.object(main.gmail_client, "send", side_effect=[ConnectionError("down"), "thread"]) as send:
            main._announce_state(state)
            self.assertNotIn("banner_state", state)
            main._announce_state(state)
            self.assertEqual(state["banner_state"], "E2E")
            self.assertEqual(send.call_count, 2)

    def test_only_confirmed_merge_gets_the_merge_diagram(self):
        for merged in (False, True):
            state = {"state": "WAIT_MERGE", "item": "task", "slug": "task"}
            with self.subTest(merged=merged), \
                 patch.object(main.task_source, "mark_done", return_value=True), \
                 patch.object(main, "email") as send:
                main._finish_task(state, "Finished", reset_repo=False, merged=merged)
            self.assertEqual(send.call_args.kwargs.get("milestone"),
                             "merged" if merged else None)
