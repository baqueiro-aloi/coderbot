import unittest
from operations import Budget, budget, remaining


class BudgetTests(unittest.TestCase):
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
