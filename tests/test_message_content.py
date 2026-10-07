"""Questions and conversational context must not require opening an attachment."""
import base64
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import Mock, patch

import tests
with patch.dict(sys.modules, {'gdoc_client': Mock(), 'task_source': Mock(), 'gmail_client': Mock()}):
    import main
import message_content
import diagnostics
import gmail_client
import slack_client
from execution_store import ExecutionStore


class ConversationContentTests(unittest.TestCase):
    def test_technical_json_is_removed_without_losing_question_or_options(self):
        text = ('Necesito decidir cómo continuar.\n'
                '{\n  "checks": [{"status": "fail"}]\n}\n'
                '¿Reparamos la dependencia o detenemos esta tarea?\n'
                '- Reparar: conserva el alcance.\n- Detener: no habrá PR.')
        visible, removed = message_content.split(text)
        self.assertTrue(removed)
        self.assertNotIn('"checks"', visible)
        self.assertIn('¿Reparamos', visible)
        self.assertIn('Detener: no habrá PR', visible)

    def test_conversational_text_codeblock_and_inline_braces_are_preserved(self):
        text = 'Propongo {esta opción}.\n```text\nA: conservar datos\nB: detener\n```\n¿Qué prefieres?'
        self.assertEqual(message_content.split(text), (text, False))

    def test_long_question_and_context_stay_in_body_for_both_channels(self):
        for channel in ('slack', 'email'):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as root:
                directory = Path(root)
                state = {'state': 'EXPLORING', 'slug': 'task', 'item': 'task', 'thread_id': 'C:1'}
                context = 'Contexto necesario para decidir:\n' + '- Consecuencia importante.\n' * 90
                question = '¿Prefieres conservar los datos o empezar una migración?'
                result = SimpleNamespace(session_id='session', output=context + question,
                                         preamble=context, question=question, attachments=[])
                store = ExecutionStore(directory / 'db')
                with patch.object(main.config, 'COMM_CHANNEL', channel), \
                     patch.object(main.config, 'DATA_DIR', directory), \
                     patch.object(main.phase_checkpoint, 'store', return_value=store), \
                     patch.object(main, 'trail'), patch.object(main, '_transcript_append'), \
                     patch.object(main, '_transcript_note'), \
                     patch.object(main.gmail_client, 'deliver', return_value={'thread_id': 'C:1'}) as deliver:
                    main.handle_result(state, result, 'EXPLORING')
                body = deliver.call_args.args[2]
                self.assertIn(context, body)
                self.assertIn(question, body)
                self.assertIn(question, state['last_email']['body'])
                file = deliver.call_args.args[4][0]
                self.assertEqual(file.suffix, '.txt')
                self.assertIn(context, file.read_text())
                self.assertNotIn('"detail":', file.read_text())

    def test_long_important_message_keeps_final_decision_and_links(self):
        with tempfile.TemporaryDirectory() as root:
            state = {'state': 'WAIT_REPLY', 'item': 'task', 'slug': 'task', 'thread_id': 'C:1'}
            body = 'Explicación:\n' + '- Detalle importante.\n' * 120 + '\nDecisión: conserva el plan. https://example.test/pr'
            with patch.object(main.config, 'DATA_DIR', Path(root)), patch.object(main, 'trail'), \
                 patch.object(main.phase_checkpoint, 'store', return_value=ExecutionStore(Path(root) / 'db')), \
                 patch.object(main.gmail_client, 'deliver', return_value={'thread_id': 'C:1'}) as deliver:
                main.email(state, 'Important update', body)
            self.assertIn(body, deliver.call_args.args[2])

    def test_diagnostic_detail_is_readable_not_json_escaped(self):
        with tempfile.TemporaryDirectory() as root:
            text = 'Primera línea\nSegunda línea\n¿Continuamos?'
            file = diagnostics.report(ExecutionStore(Path(root) / 'db'), {'item': 'task'}, root, root,
                                      'question', detail=text)
            self.assertIn(text, file.read_text())
            self.assertNotIn('Primera línea\\n', file.read_text())

    def test_actual_slack_posts_question_and_context_across_chunks(self):
        web = Mock()
        text = 'Contexto importante.\n' * 400 + '¿Qué opción prefieres?'
        with patch.object(slack_client, 'web', return_value=web):
            slack_client.send('Question', text, 'C:1')
        posted = ''.join(call.kwargs['text'] for call in web.chat_postMessage.call_args_list)
        self.assertIn('¿Qué opción prefieres?', posted)
        self.assertEqual(posted.count('Contexto importante.'), 400)
        self.assertGreater(web.chat_postMessage.call_count, 1)

    def test_actual_email_mime_contains_question_and_context_in_body(self):
        service = Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
            'id': 'sent', 'threadId': 'thread'}
        text = 'Contexto importante.\n' * 200 + '¿Qué opción prefieres?'
        with patch.object(gmail_client, '_gmail', return_value=service):
            gmail_client.send('Question', text)
        raw = service.users.return_value.messages.return_value.send.call_args.kwargs['body']['raw']
        message = BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw))
        self.assertIn(text, message.get_body(preferencelist=('plain',)).get_content())
        self.assertIn('¿Qué opción prefieres?', message.get_body(preferencelist=('html',)).get_content())

    def test_visible_question_is_not_lost_after_technical_payload(self):
        with tempfile.TemporaryDirectory() as root:
            state = {'state': 'VERIFYING', 'item': 'task', 'slug': 'task', 'thread_id': 'C:1'}
            question = '¿Reparamos la dependencia?\n- Sí: repetir el check.\n- No: pausar.'
            with patch.object(main.config, 'DATA_DIR', Path(root)), patch.object(main, 'trail'), \
                 patch.object(main.phase_checkpoint, 'store', return_value=ExecutionStore(Path(root) / 'db')), \
                 patch.object(main.gmail_client, 'deliver', return_value={'thread_id': 'C:1'}) as deliver:
                main.email(state, 'Verification blocked', '{"status":"infrastructure"}', visible_question=question)
            self.assertIn(question, deliver.call_args.args[2])
            self.assertNotIn('How should we resolve', deliver.call_args.args[2])
            self.assertNotIn('"status"', deliver.call_args.args[2])
