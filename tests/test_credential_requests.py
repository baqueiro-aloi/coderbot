import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from check_plan import Check
import credential_requests as credentials
import main
import validation_overrides


class CredentialRequestTests(unittest.TestCase):
    def check(self):
        return Check('service:live', ['live-test'], kind='upstream', contract_version=2,
                     max_age_seconds=60, external_dependencies=['service'], env_keys=['SERVICE_KEY'])

    def request(self):
        return {'version': 1, 'service': 'service', 'environment': 'staging',
            'env_keys': ['SERVICE_KEY'], 'permissions': ['inference'], 'check_ids': ['service:live'],
            'effects': 'synthetic inference', 'paid': True, 'max_cost': 0.05, 'currency': 'USD'}

    def test_request_requires_existing_checks_and_explicit_budget(self):
        self.assertEqual(credentials.validate(self.request(), [self.check()])['service'], 'service')
        for field, value in (('check_ids', ['unknown']), ('paid', 'yes'), ('max_cost', -1),
                             ('environment', ''), ('env_keys', ['OTHER_KEY'])):
            request = {**self.request(), field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                credentials.validate(request, [self.check()])

    def test_options_include_continuation_without_key_and_no_plaintext_request(self):
        question = credentials.question(self.request())
        self.assertIn('continue without', question.lower())
        self.assertIn('0.05', question)
        self.assertIn('SERVICE_KEY', question)
        self.assertIn('one-time', question)
        self.assertIn('keep paused', question.lower())
        self.assertIn('do not send a one-time link', question.lower())

    def test_request_cannot_include_unrelated_local_check_in_omission_scope(self):
        local = Check('service:local', ['local-test'])
        request = {**self.request(), 'check_ids': ['service:live', 'service:local']}
        with self.assertRaises(ValueError):
            credentials.validate(request, [self.check(), local])

    def test_authorized_exception_prevents_reasking_same_requirement(self):
        state = {}
        validation_overrides.authorize(state, [self.check()], ['service:live'], message_id='m',
            author='u', instruction='No key, continue', reason='explicit')
        self.assertFalse(credentials.missing(self.request(), [self.check()], state, environ={}))
        self.assertTrue(credentials.missing(self.request(), [self.check()], {}, environ={}))
        self.assertFalse(credentials.missing({**self.request(), 'paid': False, 'max_cost': 0},
            [self.check()], {}, environ={'SERVICE_KEY': 'value'}))

    def test_controller_asks_during_exploration_without_executing_paid_check(self):
        state = {'state': 'EXPLORING', 'slug': 'task', 'item': 't'}
        output = 'CREDENTIAL_REQUEST: ' + json.dumps(self.request()) + '\nCHECK_PLAN: ' + json.dumps({
            'version': 2, 'checks': [self.check().to_dict()]})
        result = SimpleNamespace(session_id='s', output=output, question=None, attachments=[])
        with patch.object(main, 'save_state'), patch.object(main, 'email') as email, \
             patch.object(main.checks, 'execute_plan') as execute, \
             patch.dict('os.environ', {}, clear=True):
            self.assertTrue(main.handle_result(state, result, 'EXPLORING'))
        execute.assert_not_called()
        self.assertEqual(state['state'], 'WAIT_REPLY')
        self.assertEqual(state['pending_validation_checks'], ['service:live'])
        self.assertIn('continue without', email.call_args.args[2].lower())

    def test_inventory_survives_credential_question_and_override(self):
        state = {'state': 'EXPLORING', 'slug': 'task', 'item': 't'}
        output = ('INTEGRATION_INVENTORY: {"version":1,"integrations":[]}\n'
            + 'CREDENTIAL_REQUEST: ' + json.dumps(self.request()) + '\nCHECK_PLAN: '
            + json.dumps({'version': 2, 'checks': [self.check().to_dict()]}))
        result = SimpleNamespace(session_id='s', output=output, question=None, attachments=[])
        with patch.object(main, 'save_state'), patch.object(main, 'email'), \
             patch.dict('os.environ', {}, clear=True):
            main.handle_result(state, result, 'EXPLORING')
        self.assertEqual(state['integration_inventory'], {'version': 1, 'integrations': []})
        with patch.object(main.check_plan, 'discover', return_value=[]), \
             patch.object(main.gmail_client, 'message_author', return_value='user@example.test'), \
             patch.object(main.agent_runner, 'run', return_value=SimpleNamespace(output=json.dumps({
                 'action': 'omit', 'check_ids': ['service:live'], 'reason': 'declined', 'other_instructions': ''}))), \
             patch.object(main, 'save_state'), patch.object(main, 'email'):
            self.assertTrue(main._accept_validation_override(state, 'm', 'No key, continue'))
        self.assertEqual(state['state'], 'EXPLORING')
        self.assertFalse(credentials.missing(self.request(), [self.check()], state, environ={}))

    def test_budget_is_not_authorized_by_having_a_key(self):
        self.assertTrue(credentials.missing(self.request(), [self.check()], {}, environ={'SERVICE_KEY': 'present'}))

    def test_partial_exception_does_not_reask_omitted_key(self):
        other = Check('service:other', ['other-test'], env_keys=['OTHER_KEY'], contract_version=2)
        plan, state = [self.check(), other], {}
        request = {**self.request(), 'paid': False, 'max_cost': 0,
                   'env_keys': ['SERVICE_KEY', 'OTHER_KEY'], 'check_ids': ['service:live', other.id]}
        credentials.validate(request, plan)
        validation_overrides.authorize(state, plan, ['service:live'], message_id='m', author='u',
            instruction='omit service live only', reason='explicit')
        self.assertFalse(credentials.missing(request, plan, state, environ={'OTHER_KEY': 'present'}))
        self.assertTrue(credentials.missing(request, plan, state, environ={}))

    def test_resume_cannot_bypass_known_budget_by_omitting_request_marker(self):
        check = self.check()
        state = {'state': 'IMPLEMENTING', 'pending_credential_request': self.request(),
                 'reported_check_plan': [check.to_dict()]}
        result = SimpleNamespace(session_id='s', question=None, attachments=[],
            output='CHECK_PLAN: ' + json.dumps({'version': 2, 'checks': [check.to_dict()]}))
        with patch.object(main, 'save_state'), patch.object(main, 'email'), \
             patch.object(main.checks, 'execute_plan') as execute, \
             patch.dict('os.environ', {'SERVICE_KEY': 'present'}, clear=True):
            self.assertTrue(main.handle_result(state, result, 'IMPLEMENTING'))
        execute.assert_not_called()
        self.assertEqual(state['state'], 'WAIT_REPLY')

    def test_planning_check_plan_never_executes_even_without_credential_request(self):
        output = 'CHECK_PLAN: ' + json.dumps({'version': 2, 'checks': [self.check().to_dict()]})
        result = SimpleNamespace(session_id='s', output=output, question=None, attachments=[])
        with patch.object(main, '_transcript_append'), patch.object(main.checks, 'execute_plan') as execute:
            self.assertFalse(main.handle_result({'state': 'EXPLORING'}, result, 'EXPLORING'))
        execute.assert_not_called()

    def test_omitted_live_check_does_not_execute_on_implementation_resume(self):
        state = {'state': 'IMPLEMENTING'}
        check = self.check()
        validation_overrides.authorize(state, [check], [check.id], message_id='m', author='u',
            instruction='continue without key', reason='explicit')
        output = 'CHECK_PLAN: ' + json.dumps({'version': 2, 'checks': [check.to_dict()]})
        result = SimpleNamespace(session_id='s', output=output, question=None, attachments=[])
        with patch.object(main, '_transcript_append'), patch.object(main.checks, 'execute_plan', return_value=[]) as execute:
            main.handle_result(state, result, 'IMPLEMENTING')
        self.assertEqual(execute.call_args.args[0], [])
        self.assertEqual(state['focused_check_results'][0]['status'], 'not_run')

    def test_exact_omission_runs_available_local_alternative_after_state_reload(self):
        remote, local = self.check(), Check('service:local', ['local-test'], contract_version=2)
        state = {'state': 'IMPLEMENTING', 'pending_credential_request': self.request(),
                 'reported_check_plan': [remote.to_dict(), local.to_dict()]}
        validation_overrides.authorize(state, [remote, local], [remote.id],
            message_id='m', author='u', instruction='No key, continue', reason='explicit')
        state = json.loads(json.dumps(state))
        result = SimpleNamespace(session_id='s', question=None, attachments=[], output='CHECK_PLAN: '
            + json.dumps({'version': 2, 'checks': [remote.to_dict(), local.to_dict()]}))
        with patch.object(main, '_transcript_append'), \
             patch.object(main.checks, 'execute_plan', return_value=[{'check': local.id, 'status': 'pass'}]) as execute, \
             patch.dict('os.environ', {}, clear=True):
            self.assertFalse(main.handle_result(state, result, 'IMPLEMENTING'))
        self.assertEqual(execute.call_args.args[0], [local])
        outcomes = {row['check']: row for row in state['focused_check_results']}
        self.assertEqual(outcomes[local.id]['status'], 'pass')
        self.assertEqual(outcomes[remote.id]['status'], 'not_run')
        self.assertEqual(outcomes[remote.id]['gate']['status'], 'accepted_exception')
