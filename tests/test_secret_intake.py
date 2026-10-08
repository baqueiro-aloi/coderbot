import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config
from check_plan import Check
import secret_intake
import secret_safety
from private_secrets import PrivateSecrets


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(secret_safety.clear)
        patcher = patch.object(config, 'DATA_DIR', Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.check = Check('live', ['test'], env_keys=['SERVICE_KEY'])
        self.request = {'env_keys': ['SERVICE_KEY'], 'check_ids': ['live']}
        self.url = 'https://bin.example/?0123456789abcdef#' + '2' * 44

    def test_link_never_reaches_general_text_without_bound_context(self):
        text = secret_intake.sanitize('Here ' + self.url, 'thread', 'message')
        self.assertNotIn(self.url, text)
        self.assertNotIn('#' + '2' * 44, text)
        self.assertIn('unavailable', text)

    def test_success_and_duplicate_message_only_consume_once(self):
        secret_intake.bind('thread', 'task', self.request, [self.check])
        def receive(url, instances, private, **kwargs):
            return private.provision('synthetic-intake-value', **kwargs)
        with patch.dict('os.environ', {'CODEBOT_PRIVATEBIN_INSTANCES': '["https://bin.example/"]'}), \
             patch('privatebin_receiver.receive', side_effect=receive) as fetch:
            for _ in range(2):
                text = secret_intake.sanitize(self.url, 'thread', 'message')
                self.assertNotIn(self.url, text)
                self.assertNotIn('synthetic-intake-value', text)
            fetch.assert_called_once()
        handles = secret_intake.bindings('task', self.check)
        self.assertEqual(len(handles), 1)
        self.assertEqual(PrivateSecrets(config.DATA_DIR / 'private-secrets').resolve(
            handles[0], task_id='task', check=self.check)[1], 'synthetic-intake-value')

    def test_private_handle_satisfies_nonpaid_prerequisite_after_restart(self):
        import credential_requests
        state = {'execution_task_id': 'task'}
        request = {**self.request, 'paid': False}
        secret_intake.bind('thread', 'task', self.request, [self.check])
        def receive(url, instances, private, **kwargs):
            return private.provision('synthetic-intake-value', **kwargs)
        with patch.dict('os.environ', {'CODEBOT_PRIVATEBIN_INSTANCES': '["https://bin.example/"]'}, clear=True), \
             patch('privatebin_receiver.receive', side_effect=receive):
            secret_intake.sanitize(self.url, 'thread', 'message')
            self.assertFalse(credential_requests.missing(request, [self.check], state))
        private = PrivateSecrets(config.DATA_DIR / 'private-secrets')
        private.revoke(secret_intake.bindings('task', self.check)[0])
        with patch.dict('os.environ', {}, clear=True):
            self.assertTrue(credential_requests.missing(request, [self.check], state))

    def test_expired_context_no_consumption_and_new_message_allows_reprovision(self):
        secret_intake.bind('thread', 'task', self.request, [self.check])
        with patch('secret_intake.time.time', return_value=10**12), \
             patch('privatebin_receiver.receive') as fetch:
            self.assertIn('rejected', secret_intake.sanitize(self.url, 'thread', 'message'))
        fetch.assert_not_called()

    def test_email_poll_sanitizes_before_return_to_controller(self):
        import gmail_client
        from unittest.mock import Mock
        service = Mock()
        with patch.object(gmail_client, '_gmail', return_value=service), \
             patch.object(gmail_client, '_load_processed', return_value=[]), \
             patch.object(gmail_client, 'reply_candidates', return_value=iter([('message', self.url)])):
            identity, text = gmail_client.poll_reply('thread')
        self.assertEqual(identity, 'message')
        self.assertNotIn(self.url, text)

    def test_provisioned_reference_exact_scope_not_filesystem_path(self):
        secret_intake.bind('thread', 'task', self.request, [self.check])
        private = PrivateSecrets(config.DATA_DIR / 'private-secrets')
        handle = private.provision('synthetic-reference-value', task_id='task', check=self.check, env_key='SERVICE_KEY')
        text = secret_intake.sanitize('SECRET_REFERENCE: ' + handle, 'thread', 'message')
        self.assertIn('accepted', text)
        self.assertNotIn(handle, text)
        self.assertEqual(secret_intake.bindings('task', self.check), [handle])

    def test_crash_after_private_persistence_recovers_without_remote_fetch(self):
        from validation_overrides import scope
        import time
        secret_intake.bind('thread', 'task', self.request, [self.check])
        private = PrivateSecrets(config.DATA_DIR / 'private-secrets')
        handle = private.provision('synthetic-recovered-value', task_id='task', check=self.check, env_key='SERVICE_KEY')
        secret_intake._write(secret_intake._name('intake', 'message'), {'version': 1,
            'state': 'started', 'task_id': 'task', 'handles': {scope(self.check): [handle]}, 'expires': time.time() + 100})
        with patch('privatebin_receiver.receive') as fetch:
            self.assertIn('securely received', secret_intake.sanitize(self.url, 'thread', 'message'))
        fetch.assert_not_called()
        self.assertEqual(secret_intake.bindings('task', self.check), [handle])

    def test_private_storage_failure_redacts_link_and_preserves_task(self):
        with patch('secret_intake._private', side_effect=OSError('unavailable')):
            text = secret_intake.sanitize(self.url, 'thread', 'message')
        self.assertNotIn(self.url, text)
        self.assertIn('unavailable', text)

    def test_crash_window_never_retries_consumed_link(self):
        secret_intake.bind('thread', 'task', self.request, [self.check])
        with patch.dict('os.environ', {'CODEBOT_PRIVATEBIN_INSTANCES': '["https://bin.example/"]'}), \
             patch('privatebin_receiver.receive', side_effect=RuntimeError('consumed then failed')) as fetch:
            first = secret_intake.sanitize(self.url, 'thread', 'message')
            second = secret_intake.sanitize(self.url, 'thread', 'message')
        fetch.assert_called_once()
        self.assertIn('new link', second)
        self.assertNotIn(self.url, first + second)
        self.assertEqual(secret_intake.bindings('task', self.check), [])

    def test_slack_boundary_persists_only_sanitized_link(self):
        import slack_client
        with patch.object(config, 'SLACK_CHANNEL_ID', 'C1'):
            with slack_client._database() as db:
                db.execute('INSERT INTO roots VALUES(?,?,?)', ('C1', '1', 'nonce'))
            slack_client._accept_event({'event': {'type': 'message', 'channel': 'C1', 'user': 'U1',
                'ts': '2', 'thread_ts': '1', 'text': self.url}})
            with slack_client._database() as db:
                text = db.execute('SELECT text FROM messages').fetchone()[0]
                self.assertNotIn(self.url, text)
                self.assertIn('[REDACTED]', text)
