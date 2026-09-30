import unittest
from check_plan import parse, reported
from check_results import parse_output


class CheckPlanTests(unittest.TestCase):
    def test_reported_plan_requests_real_execution(self):
        self.assertEqual(reported("QUALITY_GATE: {}"), [])
        plan = reported('summary\nCHECK_PLAN: {"version":1,"checks":[{"id":"unit","argv":["test"],"scope":"focused"}]}')
        self.assertEqual(plan[0].scope, "focused")
    def test_unknown_output_never_becomes_identifiable_failure(self):
        self.assertEqual(parse_output("connection failed", 1, "unittest")["status"], "unknown")
        result = parse_output("FAIL: test_x (tests.X)\n----------------------------------------------------------------------\nAssertionError: bad\n----------------------------------------------------------------------\nRan 1 test in 0.1s\nFAILED", 1, "unittest")
        self.assertEqual(result["status"], "fail")
        self.assertIn("test_x (tests.X)", result["failures"])
    def test_trusted_external_command_is_valid_without_approval(self):
        checks = parse({"version": 1, "checks": [{"id": "external", "argv": ["/opt/tools/test"],
            "cwd": "/scratch/worktree", "resources": ["port:8111"], "timeout": 30}]})
        self.assertEqual(checks[0].cwd, "/scratch/worktree")

    def test_invalid_or_duplicate_plan_is_rejected(self):
        for value in ({"version": 2, "checks": []},
                      {"version": 1, "checks": [{"id": "x", "argv": []}]},
                      {"version": 1, "checks": [{"id": "x", "argv": ["a"]}] * 2}):
            with self.assertRaises(ValueError):
                parse(value)
