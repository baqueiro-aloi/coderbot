"""Controlled adapters exercise feedback, replan and diagnostic delivery together."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"task_source": Mock(), "gdoc_client": Mock(), "gmail_client": Mock()}):
    import main
import feedback
from execution_store import ExecutionStore
import message_delivery
import gmail_client
import slack_client


class ConversationFlowTests(unittest.TestCase):
    def test_feedback_replan_and_failure_report_in_both_adapters(self):
        for channel, backend in (("email", gmail_client), ("slack", slack_client)):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as root:
                repo = Path(root)
                store = ExecutionStore(repo / "db")
                state = {"item": "Models", "slug": "models", "branch": "feature",
                         "state": "ADDRESS_PR_THREADS", "session_id": "s", "thread_id": "C:1"}
                feedback.receive(store, state, repo, "user-message", "Missing model dropdown; part of the feature")
                assessment = '{"action":"replan","answer":"Selector is missing.","reason":"Provider/session design changes.","references":"design.md;toolbar.tsx"}'
                api = Mock()
                api.files_upload_v2.return_value = {"files": [{"id": "F1"}]}
                api.chat_postMessage.return_value = {"ts": "2"}
                with patch.object(main.config, "REPO_PATH", repo), patch.object(main.config, "DATA_DIR", repo), \
                     patch.object(main.phase_checkpoint, "store", return_value=store), \
                     patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=assessment)), \
                     patch.object(main, "email"), patch.object(main, "save_state"):
                    main._dispatch_feedback(state)
                self.assertEqual(state["state"], "REPLANNING")
                from diagnostics import report
                artifact = report(store, state, repo, repo, "RECOVERING", error=RuntimeError("complete diagnostic"))
                with patch.object(slack_client, "web", return_value=api), \
                     patch.object(gmail_client, "send", return_value="C:1") as email:
                    receipt = message_delivery.deliver(store, state, repo, repo, backend,
                        "Recovery incident", "Work is preserved; recovery will continue.", "C:1", [artifact])
                    self.assertTrue(receipt["complete"])
                    reopened = ExecutionStore(repo / "db")
                    message_delivery.retry_pending(reopened, state, repo, backend)
                    if channel == "slack":
                        api.files_upload_v2.assert_called_once()
                        api.chat_postMessage.assert_called_once()
                    else:
                        self.assertEqual(email.call_count, 2)
                        self.assertEqual(email.call_args.args[3], [artifact])
