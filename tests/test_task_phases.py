import json
from pathlib import Path
import tempfile
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main
import task_phases


class TaskPhaseTests(unittest.TestCase):
    def test_pending_implementation_returns_to_work_without_consuming_gate_retries(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Implement cancellation\n- [ ] 2. [codebot:final-checks] Run suite\n")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"):
                main._complete_verify(state, SimpleNamespace(output="incomplete"))
            self.assertEqual(state["state"], "IMPLEMENTING")
            self.assertNotIn("verify_round", state)
            self.assertIn("Implement cancellation", state["implementation_feedback"])

    def test_explicit_controller_task_can_wait_until_final_checks_pass(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [x] 1. Implement\n- [ ] 2. [codebot:final-checks] Run suite\n")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            output = 'QUALITY_GATE: ' + json.dumps({"status": "pass", "openspec": "pass",
                "commands": ["focused: pass"], "tasks": "1/2", "deferred": 1})
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
                 patch.object(main, "_run_checked", side_effect=["valid", json.dumps({"state": "ready",
                     "progress": {"total": 2, "complete": 1, "remaining": 1}})]):
                main._complete_verify(state, SimpleNamespace(output=output))
            self.assertEqual(state["state"], "INTERNAL_REVIEW")
            self.assertEqual(len(task_phases.inspect(root, "task")["final_checks"]), 1)
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), patch.object(main, "save_state"), \
                 patch.object(main, "announce_milestone"), \
                 patch.object(main, "_gate_failed"), \
                 patch.object(main.final_checks, "run", return_value={"status": "indeterminate", "checks": []}):
                main.do_e2e(state)
            self.assertEqual(len(task_phases.inspect(root, "task")["final_checks"]), 1)
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), patch.object(main, "save_state"), \
                 patch.object(main, "announce_milestone"), \
                 patch.object(main.final_checks, "run", return_value={"status": "pass", "checks": []}):
                main.do_e2e(state)
            self.assertEqual(task_phases.inspect(root, "task")["complete"], 2)
            self.assertEqual(state["state"], "ARCHIVING")

    def test_incomplete_count_cannot_pass_without_explicit_defer_count(self):
        output = 'QUALITY_GATE: ' + json.dumps({"status": "pass", "openspec": "pass",
            "commands": ["focused: pass"], "tasks": "1/2"})
        self.assertIsNone(main.parse_quality_gate(output)[0])
