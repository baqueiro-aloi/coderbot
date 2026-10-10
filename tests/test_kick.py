"""KICK interrupts one turn, preserves the task checkpoint and never acts as ABORT."""
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import agent_runner
import claude_runner
import config
import turn_control

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main


class ProcessInterruption(unittest.TestCase):
    def test_opencode_stream_exits_promptly_as_kicked_not_failed(self):
        started = threading.Event()
        outcome = []

        def run():
            try:
                agent_runner._run_streaming(
                    [sys.executable, "-c", "import time; print('started',flush=True); time.sleep(30)"],
                    cwd=None, env=dict(os.environ), timeout=20,
                    on_line=lambda _: started.set())
            except BaseException as error:
                outcome.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(started.wait(3))
            began = time.monotonic()
            self.assertTrue(turn_control.request_kick())
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertLess(time.monotonic() - began, 5)
            self.assertEqual(len(outcome), 1)
            self.assertIsInstance(outcome[0], turn_control.TurnKicked)
            self.assertFalse(turn_control.request_kick())
        finally:
            worker.join(timeout=5)

    def test_claude_communicate_exits_as_kicked(self):
        outcome = []
        def run():
            try:
                claude_runner._run([sys.executable, "-c", "import time; time.sleep(30)"])
            except BaseException as error:
                outcome.append(error)
        with patch.object(config, "REPO_PATH", Path.cwd()):
            worker = threading.Thread(target=run)
            worker.start()
            try:
                for _ in range(100):
                    if turn_control.request_kick():
                        break
                    time.sleep(0.01)
                else:
                    self.fail("the Claude process never became interruptible")
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(outcome), 1)
                self.assertIsInstance(outcome[0], turn_control.TurnKicked)
            finally:
                worker.join(timeout=5)


class StateRecovery(unittest.TestCase):
    def test_kicked_tick_reloads_checkpoint_without_failure_budget(self):
        saved = []
        checkpoint = {"state": "IMPLEMENTING", "item": "task", "slug": "task",
                      "thread_id": "C1:1", "session_id": "session", "task_language": "English"}
        with patch.object(main, "load_state", side_effect=[dict(checkpoint), dict(checkpoint),
                                                          dict(checkpoint, kick_pending=True)]), \
             patch.object(main, "save_state", side_effect=lambda state: saved.append(dict(state))), \
             patch.object(main, "_announce_state"), \
             patch.object(main, "check_commands", return_value=False), \
             patch.object(main, "_maybe_ping"), \
             patch.object(main.agent_runner, "set_task_context"), \
             patch.object(main.agent_runner, "set_task_language"), \
             patch.dict(main.PHASES, {"IMPLEMENTING": Mock(side_effect=[
                 turn_control.TurnKicked(), SystemExit("stop")])}):
            with self.assertRaisesRegex(SystemExit, "stop"):
                main._run_loop()
        self.assertEqual(saved[0]["kick_count"], 1)
        self.assertTrue(saved[0]["kick_pending"])
        self.assertEqual(saved[0]["state"], "IMPLEMENTING")
        self.assertEqual(saved[0]["session_id"], "session")
        self.assertNotIn("failures", saved[0])
        self.assertFalse(main._work_active.is_set())

    def test_recovery_prompt_inspects_actual_files_before_continuing(self):
        state = {"kick_pending": True, "branch": "b", "state": "IMPLEMENTING"}
        agent_runner.set_task_context(state)
        try:
            with patch.object(config, "AGENT", "opencode"), \
                 patch.object(agent_runner.phase_checkpoint, "replay", return_value=None), \
                 patch.object(agent_runner.phase_checkpoint, "record"), \
                 patch.object(agent_runner, "_opencode", return_value=Mock()) as call:
                agent_runner.resume("ses", "continue")
            prompt = call.call_args.args[0]
            self.assertIn("actual git working tree", prompt)
            self.assertIn("completed tasks", prompt)
            self.assertIn("continue", prompt)
        finally:
            agent_runner.set_task_context(None)

    def test_no_running_turn_is_a_noop_not_abort(self):
        state = {"state": "WAIT_APPROVAL", "item": "task", "thread_id": "t",
                 "slug": "task"}
        with patch.object(main.gmail_client, "poll_command",
                          return_value=("m1", "t", "KICK", False, "")), \
             patch.object(main.gmail_client, "mark_processed") as processed, \
             patch.object(main.gmail_client, "send") as send, \
             patch.object(main, "_abort_and_reset") as abort:
            self.assertFalse(main.check_commands(state))
        abort.assert_not_called()
        processed.assert_called_once_with("m1")
        self.assertIn("no coding-agent turn", send.call_args.args[1].lower())
        self.assertEqual(state["state"], "WAIT_APPROVAL")
