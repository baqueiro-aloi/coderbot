import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from check_plan import discover, parse, reported
from check_results import parse_output


class CheckPlanTests(unittest.TestCase):
    def test_eslint_counts_every_error_and_keeps_semantic_messages(self):
        output = "/repo/src/a.ts\n  19:38  error  Bad regex  no-control-regex\n\n/repo/src/b.ts\n  2:4  error  Missing cause  preserve-caught-error\n\n✖ 2 problems (2 errors, 0 warnings)"
        result = parse_output(output, 1, "eslint")
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failures"]["/repo/src/a.ts:19:38:no-control-regex"], "Bad regex")
        self.assertEqual(parse_output(output.replace("2 errors", "3 errors"), 1, "eslint")["status"], "unknown")
    def test_discovered_python_keeps_real_virtualenv_and_shared_backend_environment(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            backend = repo / "backend"
            (backend / "tests").mkdir(parents=True)
            (repo / "PICAv1/backend/tests").mkdir(parents=True)
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(backend / ".venv")], check=True)
            plan = {c.id: c for c in discover(repo)}
            python = str(backend / ".venv/bin/python")
            self.assertEqual(plan["unit:backend"].argv[0], python)
            self.assertEqual(plan["unit:PICAv1/backend"].argv[0], python)
            result = subprocess.run([python, "-c", "import sys; print(sys.prefix)"], text=True,
                                    capture_output=True, check=True)
            self.assertEqual(Path(result.stdout.strip()).resolve(), (backend / ".venv").resolve())

    def test_missing_test_dependencies_are_infrastructure_not_baseline_failures(self):
        result = parse_output("ERROR: test_api\nModuleNotFoundError: No module named 'fastapi'\nRan 1 test in 0.1s", 1, "unittest")
        self.assertEqual(result["status"], "infrastructure")
        self.assertEqual(result["failures"], {})
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
