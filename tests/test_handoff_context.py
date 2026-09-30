import unittest
from handoff_context import render


class HandoffTests(unittest.TestCase):
    def test_context_is_bounded_and_contains_current_requirements_and_reports(self):
        output = render({"item": "Task", "item_detail": "a" * 100000,
                         "implementation_summary": "b" * 100000,
                         "final_check_report": {"checks": [{"check": "unit", "status": "pass", "report": "/outbox/log"}]}},
                        "INTERNAL_REVIEW")
        self.assertLess(len(output), 17000)
        self.assertIn("/outbox/log", output)
        self.assertIn("INTERNAL_REVIEW", output)
