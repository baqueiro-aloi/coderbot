import unittest
from check_plan import parse


class CheckPlanTests(unittest.TestCase):
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
