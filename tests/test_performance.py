import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import performance
from execution_store import ExecutionStore


class PerformanceTests(unittest.TestCase):
    def test_events_exclude_prompts_secrets_and_reasoning(self):
        with tempfile.TemporaryDirectory() as root, patch.object(performance.config, "DATA_DIR", Path(root)):
            performance.event("t", phase="VERIFYING", secret="token", reasoning="private", prompt="text")
            data = ExecutionStore(Path(root) / "execution.sqlite").list("operation", "t")[0]["data"]
            self.assertEqual(set(data), {"at", "phase"})
