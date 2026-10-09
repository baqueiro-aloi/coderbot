import unittest
from unittest.mock import patch

import main


class FsmEvidenceWiringTests(unittest.TestCase):
    def test_e2e_gate_routes_failed_deterministic_evidence_to_repair(self):
        state = {'state': 'E2E', 'item': 'task', 'slug': 'task', 'has_e2e_harness': True}
        report = {'status': 'fail', 'checks': [{'check': 'unit', 'status': 'fail', 'gate': {'status': 'fail'}}]}
        with patch.object(main.config, 'DETERMINISTIC_CHECKS', True), \
             patch.object(main.final_checks, 'run', return_value=report) as run, \
             patch.object(main, '_scope_drift', return_value=False), patch.object(main, 'save_state'), patch.object(main, '_begin_check_repair') as repair:
            main.do_e2e(state)
        run.assert_called_once()
        repair.assert_called_once_with(state, report, resume='E2E')
        self.assertNotEqual(state['state'], 'ARCHIVING')

    def test_e2e_gate_requires_coverage_and_independent_review_report_to_pass(self):
        state = {'state': 'E2E', 'item': 'task', 'slug': 'task', 'has_e2e_harness': True}
        report = {'status': 'indeterminate', 'checks': [], 'coverage': {'status': 'indeterminate'},
                  'independent_review': 'missing_or_stale'}
        with patch.object(main.config, 'DETERMINISTIC_CHECKS', True), \
             patch.object(main.final_checks, 'run', return_value=report), \
             patch.object(main, '_scope_drift', return_value=False), patch.object(main, 'save_state'), patch.object(main, '_begin_check_repair') as repair:
            main.do_e2e(state)
        repair.assert_called_once_with(state, report, resume='E2E')
