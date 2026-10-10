"""Optional checks are skipped, never failed, when their credentials are absent."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_repair
import checks
import final_checks
import handoffs
from check_plan import Check
from execution_store import ExecutionStore


class OptionalField(unittest.TestCase):
    def test_only_a_real_true_enables_it(self):
        for value, expected in ((True, True), ("true", False), ("no", False), (1, False), (False, False)):
            with self.subTest(value=value):
                self.assertIs(Check("x", ["a"], optional=value).optional, expected)

    def test_false_is_omitted_for_rollback_compatibility(self):
        self.assertNotIn("optional", Check("x", ["a"]).to_dict())
        self.assertTrue(Check("x", ["a"], optional=True).to_dict()["optional"])
        legacy = Check("x", ["a"]).to_dict()
        self.assertEqual(Check(**legacy), Check("x", ["a"]))

    def test_missing_credentials(self):
        check = Check("x", ["a"], env_keys=["API_KEY", "OTHER"], optional=True)
        self.assertEqual(check.missing_credentials({"API_KEY": "v", "OTHER": " "}), ["OTHER"])


class Execute(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name) / "db")

    def test_optional_without_key_is_skipped_without_spawning(self):
        check = Check("live", ["pytest", "-m", "live"], env_keys=["STRIPE_KEY"], optional=True)
        with patch.object(checks, "check_environment", return_value={}), \
                patch.object(checks.operations, "run") as run:
            result = checks.execute(check, "/repo", self.store, "task")
        run.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertIn("STRIPE_KEY", result["skipped"])

    def test_required_without_key_still_runs(self):
        check = Check("live", ["pytest"], env_keys=["STRIPE_KEY"])
        with patch.object(checks, "check_environment", return_value={}), \
                patch.object(checks, "snapshot", return_value="c"), \
                patch.object(checks, "tool_versions", return_value={}), \
                patch.object(checks, "environment_revision", return_value=0), \
                patch("check_baseline.dependency_snapshot", return_value="d"), \
                patch.object(checks.operations, "run", side_effect=OSError("ran")) as run:
            result = checks.execute(check, tempfile.gettempdir(), self.store, "task")
        run.assert_called_once()
        self.assertEqual(result["status"], "infrastructure")


class Gate(unittest.TestCase):
    def test_skipped_checks_pass_the_gate_and_are_reported(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            skipped = {"status": "skipped", "skipped": "missing credential STRIPE_KEY",
                       "failures": {}, "exit_code": None, "check": "live"}
            with patch("final_checks.snapshot", return_value="c"), \
                    patch("final_checks.check_plan.discover", return_value=[Check("live", ["t"])]), \
                    patch("final_checks.checks.execute_plan", return_value=[skipped]):
                report = final_checks.run({}, root, store)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(check_repair.unresolved(report), [])
        self.assertIn("Skipped (missing credential STRIPE_KEY)",
                      handoffs.verification({"final_check_report": report}))


if __name__ == "__main__":
    unittest.main()
