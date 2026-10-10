import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import performance
from execution_store import ExecutionStore


class PerformanceTests(unittest.TestCase):
    def test_overlapping_intervals_are_not_double_counted(self):
        rows = [{"status": "complete", "data": {"started": 0, "finished": 10}},
                {"status": "complete", "data": {"started": 5, "finished": 15}},
                {"status": "running", "data": {"started": 20}}]
        result = performance.summarize(rows)
        self.assertEqual(result["accumulated_seconds"], 20)
        self.assertEqual(result["active_wall_seconds"], 15)
        self.assertEqual(result["incomplete_operations"], 1)
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
