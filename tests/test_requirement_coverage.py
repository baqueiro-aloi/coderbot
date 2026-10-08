from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from check_plan import Check
from execution_store import ExecutionStore
from execution_identity import snapshot
import requirement_coverage
import verification_ledger
import validation_overrides


class CoverageReceiptTests(unittest.TestCase):
    def test_controller_final_gate_rejects_green_suite_without_requirement_coverage(self):
        import final_checks
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            specs = repo / 'openspec/changes/demo/specs/api'
            specs.mkdir(parents=True)
            (specs / 'spec.md').write_text('### Requirement: API\n#### Scenario: auth\n')
            state = {'slug': 'demo', 'investigation_required': True}
            store = ExecutionStore(Path(root) / 'execution.sqlite')
            check = Check('unrelated', ['test'])
            with patch('check_plan.discover', return_value=[check]), \
                 patch('checks.execute_plan', return_value=[{'check': 'unrelated', 'status': 'pass'}]):
                report = final_checks.run(state, repo, store)
            self.assertEqual(report['status'], 'indeterminate')
            self.assertEqual(state['coverage_report']['requirements'][0]['status'], 'missing')

    def test_agent_claim_cannot_cover_requirement_but_receipt_or_exception_can(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            specs = repo / 'openspec/changes/demo/specs/api'
            specs.mkdir(parents=True)
            (specs / 'spec.md').write_text('### Requirement: API\n#### Scenario: auth\n')
            state = {'slug': 'demo', 'execution_task_id': 'task'}
            store = ExecutionStore(Path(root) / 'execution.sqlite')
            requirement = verification_ledger.requirements(repo, state)[0]
            check = Check('contract', ['test'], requirements=[requirement['id']], scenarios=['auth'])
            state['reported_check_plan'] = [check.to_dict()]
            with patch('check_plan.discover', return_value=[]):
                report = {'checks': [{'check': check.id, 'status': 'pass', 'identity': 'identity'}]}
                self.assertEqual(requirement_coverage.evaluate(state, repo, store, report)['status'], 'indeterminate')
                run = store.put('check_run', task_id='task', status='complete', data={'result': {
                    'check': check.id, 'status': 'pass', 'identity': 'identity', 'content': snapshot(repo)}})
                report['checks'][0]['run_id'] = run
                self.assertEqual(requirement_coverage.evaluate(state, repo, store, report)['status'], 'pass')
                (repo / 'app.py').write_text('changed')
                self.assertEqual(requirement_coverage.evaluate(state, repo, store, report)['status'], 'indeterminate')
                validation_overrides.authorize(state, [check], [check.id], message_id='m', author='u',
                    instruction='omit exact check', reason='explicit')
                report['checks'][0]['status'] = 'not_run'
                self.assertEqual(requirement_coverage.evaluate(state, repo, store, report)['status'], 'pass')
