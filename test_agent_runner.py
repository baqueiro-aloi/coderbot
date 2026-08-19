"""Focused behavior tests for the OpenCode CLI adapter."""
import subprocess
import unittest
from unittest.mock import patch

import agent_runner


class OpenCodeRunnerTests(unittest.TestCase):
    def test_collects_final_text_and_session_id(self):
        stdout = '\n'.join([
            '{"type":"step_start","sessionID":"ses_123","part":{}}',
            '{"type":"text","sessionID":"ses_123","part":{"text":"first"}}',
            '{"type":"text","sessionID":"ses_123","part":{"text":"second"}}',
        ])
        proc = subprocess.CompletedProcess([], 0, stdout, "")
        with patch("agent_runner.subprocess.run", return_value=proc):
            result = agent_runner._opencode("hello")
        self.assertEqual(result.session_id, "ses_123")
        self.assertEqual(result.output, "first\nsecond")

    def test_raises_for_opencode_error_event(self):
        proc = subprocess.CompletedProcess(
            [], 0, '{"type":"error","sessionID":"ses_123","error":"bad credentials"}', "")
        with patch("agent_runner.subprocess.run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "bad credentials"):
                agent_runner._opencode("hello")

    def test_raises_when_session_id_is_missing(self):
        proc = subprocess.CompletedProcess([], 0, '{"type":"text","part":{"text":"done"}}', "")
        with patch("agent_runner.subprocess.run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "missing sessionID"):
                agent_runner._opencode("hello")

    def test_resume_passes_session_flag(self):
        proc = subprocess.CompletedProcess(
            [], 0, '{"type":"text","sessionID":"ses_123","part":{"text":"done"}}', "")
        with patch("agent_runner.subprocess.run", return_value=proc) as run:
            agent_runner._opencode("continue", "ses_123")
        command = run.call_args.args[0]
        self.assertEqual(command[0:2], ["opencode", "run"])
        self.assertIn("--session", command)
        self.assertEqual(command[command.index("--session") + 1], "ses_123")

    def test_resume_recovers_from_missing_session(self):
        missing = subprocess.CompletedProcess([], 1, "", "Error: Session not found")
        recovered = subprocess.CompletedProcess(
            [], 0, '{"type":"text","sessionID":"ses_new","part":{"text":"done"}}', "")
        with patch.object(agent_runner.config, "AGENT", "opencode"), \
             patch("agent_runner.subprocess.run", side_effect=[missing, recovered]) as run:
            result = agent_runner.resume("ses_missing", "continue")
        self.assertEqual(result.session_id, "ses_new")
        first_command = run.call_args_list[0].args[0]
        second_command = run.call_args_list[1].args[0]
        self.assertIn("--session", first_command)
        self.assertNotIn("--session", second_command)
        self.assertIn("previous OpenCode session is unavailable", second_command[-1])

    def test_resume_does_not_recover_from_other_errors(self):
        failed = subprocess.CompletedProcess([], 1, "", "Error: authentication failed")
        with patch.object(agent_runner.config, "AGENT", "opencode"), \
             patch("agent_runner.subprocess.run", return_value=failed) as run:
            with self.assertRaisesRegex(RuntimeError, "authentication failed"):
                agent_runner.resume("ses_123", "continue")
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
