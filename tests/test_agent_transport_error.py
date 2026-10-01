import json
import subprocess
import unittest
from unittest.mock import patch

import agent_runner
from agent_errors import AgentTransportError


class AgentTransportTests(unittest.TestCase):
    def test_fetch_failure_is_typed_and_retains_full_process_output(self):
        output = json.dumps({"type": "error", "error": {"message": "fetch failed", "detail": "x" * 5000}})
        process = subprocess.CompletedProcess(["node", "bridge"], 1, output, "transport stderr")
        with patch.object(agent_runner, "_run_streaming", return_value=process), \
             patch.object(agent_runner, "_opencode_environment", return_value={}):
            with self.assertRaises(AgentTransportError) as error:
                agent_runner._opencode("work")
        self.assertEqual(error.exception.stdout, output)
        self.assertEqual(error.exception.stderr, "transport stderr")

    def test_schema_error_is_not_transport_error(self):
        process = subprocess.CompletedProcess(["node", "bridge"], 1, "invalid", "stderr")
        with patch.object(agent_runner, "_run_streaming", return_value=process), \
             patch.object(agent_runner, "_opencode_environment", return_value={}):
            with self.assertRaises(RuntimeError) as error:
                agent_runner._opencode("work")
        self.assertNotIsInstance(error.exception, AgentTransportError)
