import unittest
from operations import Budget, budget, remaining
import operations


class BudgetTests(unittest.TestCase):
    def test_tool_state_distinguishes_subagent_and_silent_test(self):
        operations.clear()
        try:
            operations.observe({"type": "tool_start", "part": {"id": "test", "tool": "bash"}})
            operations.observe({"type": "tool_start", "part": {"id": "child", "tool": "task"}})
            entries = {e["id"]: e for e in operations.snapshot()}
            self.assertEqual(entries["child"]["kind"], "subagent")
            self.assertGreater(entries["test"]["remaining"], 800)
            operations.observe({"type": "tool_use", "part": {"id": "test"}})
            self.assertEqual(len(operations.snapshot()), 1)
        finally:
            operations.clear()
    def test_retry_uses_remaining_monotonic_budget(self):
        now = [100.0]
        b = Budget(10, clock=lambda: now[0])
        self.assertEqual(b.remaining(20), 10)
        now[0] += 7
        self.assertEqual(b.remaining(20), 3)
        now[0] += 4
        with self.assertRaises(TimeoutError):
            b.remaining()

    def test_nested_budget_cannot_extend_parent(self):
        with budget(1):
            with budget(100):
                self.assertLessEqual(remaining(100), 1)
