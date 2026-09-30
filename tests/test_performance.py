import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import performance
from execution_store import ExecutionStore


class PerformanceTests(unittest.TestCase):
    def test_status_includes_controller_operation_without_llm(self):
        import main
        import operations
        id = operations.begin("check", "unit suite", 30)
        try:
            with patch.object(main.agent_runner, "run") as run:
                text = main._short_status({"state": "E2E", "item": "t", "task_language": "Spanish"}, {}, 1)
            self.assertIn("unit suite", text)
            self.assertIn("presupuesto restante", text)
            run.assert_not_called()
        finally:
            operations.finish(id)
    def test_events_exclude_prompts_secrets_and_reasoning(self):
        with tempfile.TemporaryDirectory() as root, patch.object(performance.config, "DATA_DIR", Path(root)):
            performance.event("t", phase="VERIFYING", secret="token", reasoning="private", prompt="text")
            data = ExecutionStore(Path(root) / "execution.sqlite").list("operation", "t")[0]["data"]
            self.assertEqual(set(data), {"at", "phase"})
