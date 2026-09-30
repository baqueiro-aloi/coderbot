from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import agent_runner
import phase_checkpoint


class CheckpointReplayTests(unittest.TestCase):
    def test_crash_before_fsm_save_replays_completed_turn_not_agent(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(phase_checkpoint.config, "DATA_DIR", Path(root) / "data"), \
             patch.object(phase_checkpoint.config, "REPO_PATH", Path(root)), \
             patch.object(agent_runner.config, "AGENT", "opencode"), \
             patch("agent_runner._opencode", return_value=agent_runner.OpenCodeResult("sid", "done")) as run:
            state = {"state": "IMPLEMENTING", "branch": "feature", "item": "task"}
            subprocess.run(["git", "init", "-q", root], check=True)
            (Path(root) / ".gitignore").write_text("data/\n")
            agent_runner.set_task_context(state)
            try:
                first = agent_runner.resume("old", "implement")
                second = agent_runner.resume("old", "implement")
                self.assertEqual(first.output, second.output)
                self.assertEqual(run.call_count, 1)
                phase_checkpoint.retire(state, "IMPLEMENTING")
                agent_runner.resume("sid", "implement")
                self.assertEqual(run.call_count, 2)
            finally:
                agent_runner.set_task_context(None)
