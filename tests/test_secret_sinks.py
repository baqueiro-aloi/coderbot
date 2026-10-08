"""Synthetic leakage regressions at persistence and model/log boundaries."""
import io
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import secret_safety
from execution_store import ExecutionStore


class SecretSinkTests(unittest.TestCase):
    def setUp(self):
        secret_safety.register('synthetic-sink-secret')
        self.addCleanup(secret_safety.clear)

    def test_store_put_and_record_redact_before_sqlite(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / 'db')
            for action in (lambda: store.put('checkpoint', task_id='t',
                            data={'output': 'synthetic-sink-secret'}),
                           lambda: store.record('feedback', {'branch': 'b'}, root, 'message',
                            {'original_text': 'synthetic-sink-secret'})):
                action()
            with store.connection() as db:
                for entity in ('checkpoint', 'feedback'):
                    raw = db.execute(f'SELECT data FROM {entity}').fetchone()[0]
                    self.assertNotIn('synthetic-sink-secret', raw)

    def test_log_filter_redacts_message_and_exception(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(secret_safety.SecretFilter())
        logger = logging.getLogger('synthetic-secret-sink')
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        try:
            raise ValueError('synthetic-sink-secret')
        except ValueError:
            logger.error('output %s', 'synthetic-sink-secret', exc_info=True)
        self.assertNotIn('synthetic-sink-secret', output.getvalue())
        self.assertIn('ValueError', output.getvalue())

    def test_model_prompt_redacted_before_runner(self):
        import agent_runner
        with patch.object(agent_runner.config, 'AGENT', 'claude'), \
             patch.object(agent_runner.claude_runner, 'run', return_value=Mock(
                 session_id='s', output='ok')) as run:
            agent_runner.run('message synthetic-sink-secret', contract=False)
        self.assertNotIn('synthetic-sink-secret', run.call_args.args[0])

    def test_check_report_and_result_redact(self):
        import subprocess
        import sys
        from check_plan import Check
        from checks import execute
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root) / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            store = ExecutionStore(Path(root) / 'data/db')
            check = Check('test', [sys.executable, '-c', "print('synthetic-sink-secret')"])
            result = execute(check, repo, store, 't')
            self.assertNotIn('synthetic-sink-secret', Path(result['report']).read_text())

    def test_slack_inbox_redacts_before_commit(self):
        import slack_client
        with tempfile.TemporaryDirectory() as root, \
             patch.object(slack_client.config, 'DATA_DIR', Path(root)), \
             patch.object(slack_client.config, 'SLACK_CHANNEL_ID', 'C1'):
            with slack_client._database() as db:
                db.execute('INSERT INTO roots VALUES(?,?,?)', ('C1', '1', 'nonce'))
            slack_client._accept_event({'event': {'type': 'message', 'channel': 'C1',
                'user': 'U1', 'ts': '2', 'thread_ts': '1', 'text': 'synthetic-sink-secret'}})
            with slack_client._database() as db:
                self.assertNotIn('synthetic-sink-secret', db.execute('SELECT text FROM messages').fetchone()[0])

    def test_channel_transports_redact_before_sending(self):
        import base64
        from email.parser import BytesParser
        from email.policy import default
        import gmail_client
        import slack_client
        service, web = Mock(), Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {'id': 'sent', 'threadId': 't'}
        with patch.object(gmail_client, '_gmail', return_value=service), patch.object(slack_client, 'web', return_value=web):
            gmail_client.send('synthetic-sink-secret', 'body synthetic-sink-secret')
            slack_client.send('subject', 'body synthetic-sink-secret', 'C:1')
        raw = service.users.return_value.messages.return_value.send.call_args.kwargs['body']['raw']
        mail = BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw))
        self.assertNotIn('synthetic-sink-secret', str(mail))
        self.assertNotIn('synthetic-sink-secret', ''.join(
            call.kwargs['text'] for call in web.chat_postMessage.call_args_list))
