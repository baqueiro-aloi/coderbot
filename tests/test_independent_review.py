import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from execution_store import ExecutionStore
import independent_review


class IndependentReviewTests(unittest.TestCase):
    def test_separate_session_receipt_and_content_binding(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'app').write_text('code')
            store = ExecutionStore(Path(root) / 'execution.sqlite')
            state = {'session_id': 'implementer', 'execution_task_id': 'task'}
            runner = Mock(return_value=SimpleNamespace(session_id='reviewer', output='{"findings":[]}'))
            state['independent_review_receipt'] = independent_review.run(state, repo, store, runner)
            self.assertTrue(independent_review.valid(state, repo, store))
            (repo / 'app').write_text('changed')
            self.assertFalse(independent_review.valid(state, repo, store))
            runner.return_value.session_id = 'implementer'
            with self.assertRaises(ValueError):
                independent_review.run(state, repo, store, runner)

    def test_important_findings_not_passed_by_implementer_claim(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            store = ExecutionStore(Path(root) / 'execution.sqlite')
            state = {'session_id': 'implementer'}
            runner = Mock(return_value=SimpleNamespace(session_id='reviewer', output=json.dumps({'findings': [
                {'severity': 'important', 'location': 'app:1', 'problem': 'unsafe', 'fix': 'gate'}]})))
            state['independent_review_receipt'] = independent_review.run(state, repo, store, runner)
            self.assertEqual(state['independent_review_receipt']['status'], 'fail')
            self.assertFalse(independent_review.valid(state, repo, store))
