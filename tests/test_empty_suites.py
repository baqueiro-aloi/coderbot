"""Suites that executed zero tests are reported; they only fail the gate when opted in."""
import tempfile
import unittest
from unittest.mock import Mock, patch

import check_repair
import config
import final_checks
import handoffs
from check_plan import Check
from check_results import parse_output
from execution_store import ExecutionStore


class Detection(unittest.TestCase):
    def zero(self, output, reporter, exit_code=0):
        return parse_output(output, exit_code, reporter).get("zero_tests", False)

    def test_explicit_zero_counts(self):
        self.assertTrue(self.zero("\n----\nRan 0 tests in 0.000s\n\nOK\n", "unittest"))
        self.assertTrue(self.zero("Ran 3 tests in 0.1s\n\nOK (skipped=3)\n", "unittest"))
        self.assertTrue(self.zero("# tests 0\n# pass 0\n# fail 0\n", "node"))
        self.assertTrue(self.zero('<testsuite tests="0"></testsuite>', "junit"))
        self.assertTrue(self.zero('<testsuite><testcase name="a"><skipped/></testcase></testsuite>', "junit"))
        self.assertTrue(self.zero('{"failures": {}, "ran": 0}', "json"))
        self.assertTrue(self.zero("  3 skipped\n", "playwright"))

    def test_real_runs_and_unrecognized_output_are_unchanged(self):
        for output, reporter in (("Ran 3 tests in 0.1s\n\nOK\n", "unittest"),
                                 ("Ran 3 tests in 0.1s\n\nOK (skipped=1)\n", "unittest"),
                                 ("# tests 4\n# pass 4\n# fail 0\n", "node"),
                                 ('<testsuite><testcase name="a"/></testsuite>', "junit"),
                                 ('{"failures": {}}', "json"),
                                 ("  2 passed\n  1 skipped\n", "playwright"),
                                 ("whatever happened", "text"),
                                 ("not xml", "junit")):
            with self.subTest(reporter=reporter, output=output):
                result = parse_output(output, 0, reporter)
                self.assertEqual(result["status"], "pass")
                self.assertNotIn("zero_tests", result)

    def test_status_never_changes(self):
        result = parse_output("Ran 0 tests in 0.000s\n\nOK\n", 0, "unittest")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["detail"], "0 tests executed")
        self.assertEqual(parse_output("Ran 0 tests in 0s\nFAILED", 1, "unittest")["status"], "unknown")


class Gate(unittest.TestCase):
    def setUp(self):
        patcher = patch("final_checks.snapshot", return_value="content")
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(__import__("pathlib").Path(tmp.name) / "db")
        self.zero = {"status": "pass", "failures": {}, "exit_code": 0, "zero_tests": True,
                     "detail": "0 tests executed", "check": "x"}

    def run_gate(self, *, flag, declared):
        discovered = [] if declared else [Check("unit:.", ["python"])]
        state = {"item": "t", "branch": "b"}
        if declared:
            state["reported_check_plan"] = [Check("api", ["pytest"]).to_dict()]
        with patch.object(config, "EMPTY_SUITE_FAILS", flag), \
                patch("final_checks.check_plan.discover", return_value=discovered), \
                patch("final_checks.checks.execute_plan", return_value=[self.zero]), \
                patch.object(self.store, "task_identity", return_value="task"):
            return final_checks.run(state, "/repo", self.store)

    def test_default_off_passes_and_reports(self):
        for declared in (False, True):
            with self.subTest(declared=declared):
                report = self.run_gate(flag=False, declared=declared)
                self.assertEqual(report["status"], "pass")
                self.assertEqual(check_repair.unresolved(report), [])
                text = handoffs.verification({"final_check_report": report})
                self.assertIn("Executed 0 tests", text)

    def test_flag_on_never_fails_discovered_suites(self):
        self.assertEqual(self.run_gate(flag=True, declared=False)["status"], "pass")

    def test_flag_on_fails_declared_checks_with_a_repairable_reason(self):
        report = self.run_gate(flag=True, declared=True)
        self.assertEqual(report["status"], "fail")
        unresolved = check_repair.unresolved(report)
        self.assertEqual([u["status"] for u in unresolved], ["not_run"])
        self.assertIn("0 tests executed", check_repair.summary(report))


if __name__ == "__main__":
    unittest.main()
