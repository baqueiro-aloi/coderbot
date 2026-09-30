from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from check_plan import Check
from execution_store import ExecutionStore
import final_checks


class FinalCheckTests(unittest.TestCase):
    def test_without_harness_still_executes_complete_unit_suite(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            plan = [Check("unit", ["python", "test"])]
            with patch("final_checks.check_plan.discover", return_value=plan), \
                 patch("final_checks.checks.execute_plan", return_value=[{"status": "pass"}]) as run:
                result = final_checks.run({"branch": "b"}, root, store)
            self.assertEqual(result["status"], "pass")
            run.assert_called_once()
