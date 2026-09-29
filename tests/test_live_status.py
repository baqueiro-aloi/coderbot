"""STATUS is answered while the main coding turn is blocked, without a second agent."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import config

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main

agent_runner = main.agent_runner
import slack_client


class AgentActivity(unittest.TestCase):
    def test_streamed_task_is_observed_without_prompt_or_output(self):
        agent_runner._begin_turn()
        try:
            event = {"type": "tool_use", "part": {"tool": "task", "state": {
                "input": {"description": "Implementar sesiones backend PICA2",
                          "prompt": "PRIVATE PROMPT"}}}}
            agent_runner._stream_line(json.dumps(event))
            snapshot = agent_runner.turn_snapshot()
            self.assertTrue(snapshot["active"])
            self.assertIn("Implementar sesiones backend PICA2", snapshot["activity"])
            self.assertNotIn("PRIVATE PROMPT", str(snapshot))
            previous = snapshot["last_activity"]
            agent_runner._stream_line(json.dumps({"type": "step_finish", "part": {}}))
            self.assertGreaterEqual(agent_runner.turn_snapshot()["last_activity"], previous)
        finally:
            agent_runner._end_turn()
        self.assertFalse(agent_runner.turn_snapshot()["active"])

    def test_failed_agent_turn_clears_active_marker(self):
        with patch.object(config, "AGENT", "claude"), \
             patch.object(agent_runner.claude_runner, "run", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                agent_runner.run("task", contract=False)
        self.assertFalse(agent_runner.turn_snapshot()["active"])


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_state = main._current_state
        self.addCleanup(setattr, main, "_current_state", self.old_state)
        self.addCleanup(main._work_active.clear)
        self.state = {"state": "IMPLEMENTING", "item": "Configurar PICA", "slug": "pica",
                      "thread_id": "C123:100.0", "task_language": "Spanish"}
        main._current_state = self.state

    def test_thread_status_answers_during_blocked_agent_and_preserves_abort(self):
        started, release = threading.Event(), threading.Event()
        def blocked_agent(_prompt, contract=False):
            started.set()
            self.assertTrue(release.wait(5))
            return Mock(output="done")
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(config, "SLACK_CHANNEL_ID", "C123"), \
             patch.object(config, "DATA_DIR", Path(self.temp.name)), \
             patch.object(config, "AGENT", "claude"), \
             patch.object(slack_client, "_bot_user", "Ubot"), \
             patch.object(slack_client, "web", return_value=MagicMock()) as web, \
             patch.object(agent_runner.claude_runner, "run", side_effect=blocked_agent) as run:
            with slack_client._database() as db:
                db.execute("INSERT INTO roots(channel,root_ts,nonce) VALUES(?,?,?)",
                           ("C123", "100.0", "task-nonce"))
            worker = threading.Thread(target=agent_runner.run, args=("task",),
                                      kwargs={"contract": False})
            worker.start()
            try:
                self.assertTrue(started.wait(2))
                main._work_active.set()
                for ts, text in (("101.0", "ABORT"), ("102.0", "status?")):
                    slack_client._accept_event({"event": {"type": "message", "ts": ts,
                                                   "thread_ts": "100.0", "channel": "C123",
                                                   "user": "Uhuman", "text": text}})
                self.assertTrue(main._status_supervisor_once())
                self.assertTrue(worker.is_alive())
                send = web.return_value.chat_postMessage.call_args.kwargs
                self.assertEqual(send["thread_ts"], "100.0")
                self.assertIn("Fase: IMPLEMENTING", send["text"])
                self.assertIn("no puedo confirmar", send["text"])
                self.assertEqual(slack_client.poll_command()[2], "ABORT")
                self.assertFalse(main._status_supervisor_once())
                run.assert_called_once()
            finally:
                release.set()
                worker.join(timeout=2)

    def test_top_level_status_gets_a_threaded_answer_even_when_idle(self):
        self.state.update(state="IDLE", item=None)
        with patch.object(config, "COMM_CHANNEL", "slack"), \
             patch.object(config, "SLACK_CHANNEL_ID", "C123"), \
             patch.object(config, "DATA_DIR", Path(self.temp.name)), \
             patch.object(slack_client, "_bot_user", "Ubot"), \
             patch.object(slack_client, "web", return_value=MagicMock()) as web:
            self.assertTrue(slack_client._accept_event({"event": {"type": "message",
                "ts": "202.0", "channel": "C123", "user": "Uhuman", "text": "status?"}}))
            self.assertTrue(main._status_supervisor_once())
            self.assertEqual(web.return_value.chat_postMessage.call_args.kwargs["thread_ts"],
                             "202.0")
            self.assertFalse(main._status_supervisor_once())

    def test_gmail_status_is_brief_without_updating_fsm_or_starting_agent(self):
        state = dict(self.state, thread_id="gmail-thread", task_language="English")
        main._current_state = state
        main._work_active.set()
        with patch.object(config, "COMM_CHANNEL", "email"), \
             patch.object(main.gmail_client, "poll_status", return_value=("m1", "gmail-thread")), \
             patch.object(main.gmail_client, "send") as send, \
             patch.object(main.gmail_client, "mark_processed") as mark, \
             patch.object(main, "save_state") as save, \
             patch.object(main.agent_runner, "run") as agent:
            self.assertTrue(main._status_supervisor_once())
        self.assertIn("Phase: IMPLEMENTING", send.call_args.args[1])
        self.assertLess(len(send.call_args.args[1]), 450)
        mark.assert_called_once_with("m1")
        save.assert_not_called()
        agent.assert_not_called()
        self.assertEqual(state["state"], "IMPLEMENTING")

    def test_stale_observation_reports_uncertainty(self):
        body = main._short_status(self.state, {"active": True, "started_at": 100.0,
                                               "last_activity": 200.0,
                                               "activity": "task: Implementar backend"}, 700.0)
        self.assertIn("hace 8 min", body)
        self.assertIn("no puedo confirmar", body)
        self.assertNotIn("Sin señales de bloqueo", body)
