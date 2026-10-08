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

    def test_one_changed_check_does_not_revoke_other_exact_bindings(self):
        plan, state = self.plan(), {}
        overrides.authorize(state, plan, ['local', 'mantle:inference'], message_id='m', author='u',
            instruction='omit both exact checks', reason='explicit')
        changed = Check('local', ['different'])
        self.assertIsNone(overrides.applicable(state, changed))
        self.assertIsNotNone(overrides.applicable(state, plan[1]))

    def test_classifier_contract_preserves_negations_and_rejects_unknown_or_mixed(self):
        self.assertEqual(overrides.classify('NO continuar sin key', self.plan())['action'], 'none')
        self.assertEqual(overrides.classify('¿continuar sin key?', self.plan())['action'], 'none')
        self.assertEqual(overrides.classify('continuar sin key si falla', self.plan())['action'], 'none')
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

    def test_legacy_waiver_without_author_cannot_skip_even_exact_named_check(self):
        state = {'check_waivers': [{'scope': 'e2e:general', 'instruction': 'skip'}]}
        check = Check('e2e:general', ['test'])
        with patch.object(final_checks.check_plan, 'discover', return_value=[check]), \
             patch.object(final_checks.checks, 'execute_plan', return_value=[{'status': 'pass'}]) as execute, \
             patch.object(final_checks, 'snapshot', return_value='snapshot'):
            final_checks.run(state, '.', type('Store', (), {'task_identity': lambda *a: 'task'})())
        self.assertEqual(execute.call_args.args[0], [check])

    def test_controller_resumes_final_gate_without_key_or_extra_approval(self):
        import main
        state = {'state': 'WAIT_REPLY', 'return_state': 'REPAIR_CHECKS',
            'check_repair': {'resume': 'E2E', 'checks': [{'check': 'mantle:inference'}]},
            'pending_question': 'Provide key or continue without inference'}
        with patch.object(main.check_plan, 'discover', return_value=self.plan()), \
              patch.object(main.gmail_client, 'message_author', return_value='user@example.test'), \
              patch.object(main, 'save_state'), patch.object(main, 'email'):
            self.assertTrue(main._accept_validation_override(state, 'message1', 'continue without key'))
        self.assertEqual(state['state'], 'E2E')
        self.assertIsNotNone(overrides.applicable(state, self.plan()[1]))

    def test_controller_negation_records_nothing(self):
        import main
        state = {'state': 'WAIT_REPLY', 'return_state': 'E2E',
                 'pending_validation_checks': ['mantle:inference']}
        with patch.object(main.check_plan, 'discover', return_value=self.plan()):
            self.assertFalse(main._accept_validation_override(state, 'message1', 'NO omitir e2e'))
        self.assertFalse(state.get('validation_overrides'))

    def test_missing_author_cannot_create_exception(self):
        import main
        state = {'state': 'WAIT_REPLY', 'return_state': 'E2E',
                 'pending_validation_checks': ['mantle:inference']}
        with patch.object(main.check_plan, 'discover', return_value=self.plan()), \
              patch.object(main.gmail_client, 'message_author', return_value=None):
            self.assertFalse(main._accept_validation_override(state, 'm', 'continue without key'))
        self.assertFalse(state.get('validation_overrides'))

    def test_slack_author_is_retained_after_restart(self):
        import slack_client
        with tempfile.TemporaryDirectory() as root, \
             patch.object(slack_client.config, 'DATA_DIR', Path(root)), \
             patch.object(slack_client.config, 'SLACK_CHANNEL_ID', 'C1'):
            with slack_client._database() as db:
                db.execute('INSERT INTO roots VALUES(?,?,?)', ('C1', '1', 'nonce'))
            slack_client._accept_event({'event': {'type': 'message', 'channel': 'C1',
                'ts': '2', 'thread_ts': '1', 'user': 'Uauthorized', 'text': 'continue without key'}})
            self.assertEqual(slack_client.message_author('C1:2'), 'Uauthorized')
            self.assertIsNone(slack_client.message_author('C1:missing'))

    def test_legacy_slack_message_migration_does_not_invent_author(self):
        import sqlite3
        import slack_client
        with tempfile.TemporaryDirectory() as root, patch.object(slack_client.config, 'DATA_DIR', Path(root)):
            with sqlite3.connect(Path(root) / 'slack_inbox.sqlite') as db:
                db.execute('CREATE TABLE messages (id TEXT PRIMARY KEY, channel TEXT NOT NULL, '
                    'root_ts TEXT NOT NULL, ts TEXT NOT NULL, text TEXT NOT NULL, '
                    'handled INTEGER NOT NULL DEFAULT 0)')
                db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)', ('C1:old', 'C1', '1', 'old', 'continue', 0))
            self.assertIsNone(slack_client.message_author('C1:old'))
            with slack_client._database() as db:
                self.assertEqual(db.execute('SELECT text FROM messages WHERE id=?', ('C1:old',)).fetchone()[0], 'continue')

    def test_email_author_must_match_configured_sender(self):
        import gmail_client
        from unittest.mock import Mock
        service = Mock()
        get = service.users.return_value.messages.return_value.get
        with patch.object(gmail_client, '_gmail', return_value=service), \
             patch.object(gmail_client.config, 'USER_EMAIL', 'owner@example.test'):
            get.return_value.execute.return_value = {'payload': {'headers': [
                {'name': 'From', 'value': 'Owner <owner@example.test>'}]}}
            self.assertEqual(gmail_client.message_author('m'), 'owner@example.test')
            get.return_value.execute.return_value = {'payload': {'headers': [
                {'name': 'From', 'value': 'stranger@example.test'}]}}
            self.assertIsNone(gmail_client.message_author('m'))
