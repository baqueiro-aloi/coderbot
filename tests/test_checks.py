from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from check_plan import Check
from checks import execute
from execution_store import ExecutionStore


class CheckRunnerTests(unittest.TestCase):
    def test_reuse_and_invalidation_for_content_and_environment(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "app.py").write_text("a")
            store = ExecutionStore(Path(root) / "data/db")
            check = Check("unit", [sys.executable, "-c", "print('ok')"], inputs=["app.py"], env_keys=["SETTING"])
            execute(check, repo, store, "t")
            self.assertTrue(execute(check, repo, store, "t")["reused"])
            (repo / "app.py").write_text("b")
            self.assertEqual(execute(check, repo, store, "t")["repetition_reason"], "content_changed")
            with patch.dict("os.environ", {"SETTING": "new"}):
                self.assertEqual(execute(check, repo, store, "t")["repetition_reason"], "environment_or_command_changed")

    def test_runs_real_process_and_retains_structured_result_and_report(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            store = ExecutionStore(Path(root) / "data/db")
            check = Check("unit", [sys.executable, "-c", "print('passed')"])
            result = execute(check, repo, store, "task")
            self.assertEqual(result["status"], "pass")
            self.assertIn("passed", Path(result["report"]).read_text())
            self.assertEqual(store.reusable_check("task", result["identity"])["data"]["result"], result)

    def test_junit_and_json_failures_are_identifiable(self):
        from check_results import parse_output
        xml = '<testsuite><testcase classname="X" name="a"><failure message="bad">trace</failure></testcase></testsuite>'
        self.assertEqual(parse_output(xml, 1, "junit")["failures"], {"X:a": "bad\ntrace"})
        self.assertEqual(parse_output('{"failures":{"a":"bad"}}', 1, "json")["status"], "fail")
