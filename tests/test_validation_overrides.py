import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from check_plan import Check
import final_checks
import validation_overrides as overrides


class OverrideTests(unittest.TestCase):
    def plan(self):
        return [Check('local', ['test']), Check('mantle:inference', ['live'],
            kind='upstream', contract_version=2, max_age_seconds=60)]

    def test_explicit_scope_persists_but_command_change_requires_review(self):
        state = {}
        receipt = overrides.authorize(state, self.plan(), ['mantle:inference'],
            message_id='m1', author='user', instruction='No puedo dar key; continúa sin prueba viva',
            reason='key unavailable')
        restored = json.loads(json.dumps(state))
        self.assertEqual(overrides.applicable(restored, self.plan()[1])['id'], receipt['id'])
        self.assertIsNone(overrides.applicable(restored, self.plan()[0]))
        changed = self.plan()[1]
        changed.argv = ['different-live']
        self.assertIsNone(overrides.applicable(restored, changed))
        self.assertEqual(restored['validation_overrides'][0]['status'], 'needs_review')

    def test_invalid_and_unknown_selection_rejected(self):
        for ids in ([], ['unknown'], ['local', 'local']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                overrides.authorize({}, self.plan(), ids, message_id='m', author='u',
                    instruction='skip requested checks', reason='explicit')

    def test_classifier_contract_preserves_negations_and_rejects_unknown_or_mixed(self):
        self.assertIn('negations', overrides.prompt('NO omitir e2e', self.plan(), 'question'))
        for verdict in ({'action': 'none'}, {'action': 'ambiguous'},
                        {'action': 'omit', 'check_ids': ['unknown'], 'reason': 'x'},
                        {'action': 'omit', 'check_ids': ['mantle:inference'], 'reason': 'x',
                         'other_instructions': 'merge now'}):
            state = {}
            self.assertFalse(overrides.accept(state, self.plan(), verdict,
                message_id='m', author='u', instruction='NO omitir e2e'))
            self.assertFalse(state.get('validation_overrides'))

    def test_gate_executes_alternatives_and_reports_omission_not_pass(self):
        plan = self.plan()
        state = {}
        overrides.authorize(state, plan, ['mantle:inference'], message_id='m', author='u',
            instruction='continue without key', reason='explicit')
        with patch.object(final_checks.check_plan, 'discover', return_value=plan), \
             patch.object(final_checks.checks, 'execute_plan', return_value=[{'status': 'pass', 'check': 'local'}]) as execute, \
             patch.object(final_checks, 'snapshot', return_value='snapshot'):
            result = final_checks.run(state, Path('/repo'), type('Store', (), {'task_identity': lambda *a: 't'})())
        self.assertEqual([c.id for c in execute.call_args.args[0]], ['local'])
        self.assertEqual(result['status'], 'pass')
        omitted = next(r for r in result['checks'] if r['check'] == 'mantle:inference')
        self.assertEqual(omitted['status'], 'not_run')
        self.assertEqual(omitted['gate']['status'], 'accepted_exception')

    def test_legacy_general_exception_does_not_skip_every_e2e_prefix(self):
        state = {'check_waivers': [{'scope': 'e2e:general', 'instruction': 'skip', 'snapshot': 'old'}]}
        plan = [Check('e2e:feature', ['feature']), Check('unit', ['unit'])]
        with patch.object(final_checks.check_plan, 'discover', return_value=plan), \
             patch.object(final_checks.checks, 'execute_plan', return_value=[{'status': 'pass'}, {'status': 'pass'}]) as execute, \
             patch.object(final_checks, 'snapshot', return_value='new'):
            final_checks.run(state, Path('/repo'), type('Store', (), {'task_identity': lambda *a: 't'})())
        self.assertEqual(len(execute.call_args.args[0]), 2)

    def test_controller_resumes_final_gate_without_key_or_extra_approval(self):
        import main
        from types import SimpleNamespace
        state = {'state': 'WAIT_REPLY', 'return_state': 'REPAIR_CHECKS',
            'check_repair': {'resume': 'E2E', 'checks': [{'check': 'mantle:inference'}]},
            'pending_question': 'Provide key or continue without inference'}
        verdict = {'action': 'omit', 'check_ids': ['mantle:inference'], 'reason': 'user declined key',
                   'other_instructions': ''}
        with patch.object(main.check_plan, 'discover', return_value=self.plan()), \
             patch.object(main.agent_runner, 'run', return_value=SimpleNamespace(output=json.dumps(verdict))), \
             patch.object(main, 'save_state'), patch.object(main, 'email'):
            self.assertTrue(main._accept_validation_override(state, 'message1', 'No puedo dar key; continúa'))
        self.assertEqual(state['state'], 'E2E')
        self.assertIsNotNone(overrides.applicable(state, self.plan()[1]))

    def test_controller_negation_records_nothing(self):
        import main
        from types import SimpleNamespace
        state = {'state': 'WAIT_REPLY', 'return_state': 'E2E',
                 'pending_validation_checks': ['mantle:inference']}
        with patch.object(main.check_plan, 'discover', return_value=self.plan()), \
             patch.object(main.agent_runner, 'run', return_value=SimpleNamespace(output='{"action":"none"}')):
            self.assertFalse(main._accept_validation_override(state, 'message1', 'NO omitir e2e'))
        self.assertFalse(state.get('validation_overrides'))
