"""Controller/worker boundaries use real durable receipts and controlled harnesses."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import markdown  # Keep extension classes outside the temporary module registry.
with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main
import parallel_conversation as lateral
from execution_store import ExecutionStore


class ParallelFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.store = ExecutionStore(self.repo / "execution.sqlite")
        self.state = {"execution_task_id": "task", "item": "Filter models", "slug": "filter",
                      "state": "WAIT_STUCK", "thread_id": "C:1", "session_id": "work",
                      "pending_question": "How should I recover?", "stuck_return": "PROPOSING",
                      "question_rounds": 2, "task_language": "Spanish"}
        for target, name, value in ((main.config, "REPO_PATH", self.repo),
                                    (main.config, "DATA_DIR", self.repo),
                                    (main.phase_checkpoint, "store", lambda: self.store)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def classify(self, text, intent="conversation", inputs=()):
        row = lateral.receive(self.store, self.state, self.repo, str(len(self.store.list("conversation", "task"))), text)
        return lateral.save_classification(self.store, row,
            {"intent": intent, "resolves_pending_question": intent == "answer", "inputs": list(inputs)})

    def test_explanation_then_valid_reply_preserves_wait_until_answer(self):
        before = copy.deepcopy(self.state)
        row = self.classify("No entiendo, ¿qué tenemos que hacer?")
        generate = Mock(return_value=SimpleNamespace(output="El proveedor bloqueó el paso.", session_id="chat"))
        deliver = Mock(return_value={"complete": True, "notification_id": "r"})
        lateral.process_one(self.store, self.repo, generate, deliver)
        self.assertEqual(self.state, before)
        self.classify("retry", "answer")
        with patch.object(main, "save_state"), patch.object(main, "_dispatch_wait_reply") as handler:
            self.assertTrue(main._dispatch_conversation(self.state))
        handler.assert_called_once()
        self.assertEqual(handler.call_args.args[2], "retry")
        self.assertEqual(self.store.get("conversation", row["id"])["status"], "complete")

    def test_stale_choice_never_authorizes_new_decision(self):
        row = self.classify("1", "answer")
        self.state["pending_question"] = "A different decision"
        with patch.object(main, "_dispatch_wait_reply") as handler:
            self.assertTrue(main._dispatch_conversation(self.state))
        handler.assert_not_called()
        self.assertNotEqual(self.store.get("conversation", row["id"])["data"]["route"], "flow")

    def test_initial_planning_change_does_not_consume_question(self):
        self.state.update(state="WAIT_REPLY", return_state="EXPLORING")
        before = copy.deepcopy(self.state)
        row = self.classify("Add provider filter", "change_request",
                            [{"kind": "change", "text": "Add provider filter"}])
        lateral.register_inputs(self.store, row, self.repo)
        lateral.transfer_changes(self.store, self.state, self.repo)
        event = self.store.list("feedback", "task")[0]
        result = SimpleNamespace(output="Planning updated", session_id="work")
        with patch.object(main.agent_runner, "resume", return_value=result) as resume, \
             patch.object(main, "save_state"), patch.object(main, "email"), \
             patch.object(main, "do_question_reply") as question:
            main._apply_received_feedback(self.state, self.store, event)
        question.assert_not_called()
        self.assertEqual(self.state, before)
        self.assertIn("does NOT answer", resume.call_args.args[1])

    def test_change_clarification_does_not_replace_workflow_question(self):
        self.state.update(state="WAIT_REPLY", return_state="IMPLEMENTING", stuck_return="IMPLEMENTING")
        before = copy.deepcopy(self.state)
        row = self.classify("Add ambiguous filter", "change_request",
                            [{"kind": "change", "text": "Add ambiguous filter"}])
        lateral.register_inputs(self.store, row, self.repo)
        lateral.transfer_changes(self.store, self.state, self.repo)
        event = self.store.list("feedback", "task")[0]
        assessment = {"action": "question", "answer": "Which provider?", "reason": "Unspecified", "references": "spec.md"}
        with patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=json.dumps(assessment))), \
             patch.object(main, "save_state"), patch.object(main, "email"), \
             patch("message_delivery.deliver", return_value={"complete": True}):
            main._apply_received_feedback(self.state, self.store, event)
        self.assertEqual(self.state, before)
        item = self.store.list("conversation_input", "task")[0]
        self.assertEqual(item["status"], "clarifying")
        self.assertEqual(item["data"]["question"], "Which provider?")

    def test_btw_never_calls_operational_handler_in_either_channel(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel), patch.object(main.config, "COMM_CHANNEL", channel), \
                 patch.object(main.gmail_client, "mark_processed"), \
                 patch.object(main, "_dispatch_wait_reply") as handler:
                self.assertTrue(main._queue_conversation(self.state, channel, "/btw abort"))
                self.assertFalse(main._dispatch_conversation(self.state))
                handler.assert_not_called()

    def test_lateral_result_for_old_task_does_not_mutate_new_task(self):
        self.classify("retry", "answer")
        new = {**self.state, "execution_task_id": "new-task"}
        with patch.object(main, "_dispatch_wait_reply") as handler:
            self.assertFalse(main._dispatch_conversation(new))
        handler.assert_not_called()

    def test_receipt_delivery_works_in_both_adapters_without_regeneration(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel):
                row = self.classify("Explain " + channel)
                row = self.store.update("conversation", row, output="Explanation", status="generated")
                backend = Mock(__name__=channel)
                backend.__name__ = channel
                backend.attachment_limits.return_value = {"file": 10000, "mime": 10000}
                def send(envelope, receipts, confirm):
                    confirm("body", {"status": "confirmed"})
                    return "C:1"
                backend.send_envelope.side_effect = send
                receipt = lateral.delivery(self.store, row, self.repo, self.repo, backend)
                self.assertTrue(receipt["complete"])
                lateral.delivery(self.store, row, self.repo, self.repo, backend)
                self.assertEqual(len(self.store.list("delivery_receipt", "task")), 1 if channel == "email" else 2)

    def test_main_delivery_barrier_blocks_before_publishing(self):
        row = self.classify("Add X", "change_request", [{"kind": "change", "text": "Add X"}])
        lateral.register_inputs(self.store, row, self.repo)
        with patch.object(main, "_receive_feedback", return_value=False), patch.object(main, "email"), \
             patch.object(main, "git") as git:
            main.do_open_pr(self.state)
        git.assert_not_called()

    def test_status_remains_available_while_lateral_worker_is_busy(self):
        main._work_active.set()
        self.addCleanup(main._work_active.clear)
        with patch.object(main, "_current_state", {**self.state, "state": "IMPLEMENTING"}), \
             patch.object(main.config, "COMM_CHANNEL", "slack"), \
             patch.object(main.agent_runner, "turn_snapshot", return_value={"active": True}), \
             patch.object(main.operations, "snapshot", return_value=[]), \
             patch.object(main.gmail_client, "poll_verify", return_value=None), \
             patch.object(main.gmail_client, "poll_kick", return_value=None), \
             patch.object(main.gmail_client, "poll_status", return_value=("status", "C:1")), \
             patch.object(main.gmail_client, "send") as send, \
             patch.object(main.gmail_client, "mark_processed"), \
             patch.object(main, "_short_status", return_value="Working"):
            self.assertTrue(main._status_supervisor_once())
        send.assert_called_once()

    def test_classified_replan_requires_approval(self):
        self.state.update(state="IMPLEMENTING")
        row = self.classify("Add provider filter", "change_request",
                            [{"kind": "change", "text": "Add provider filter"}])
        lateral.register_inputs(self.store, row, self.repo)
        lateral.transfer_changes(self.store, self.state, self.repo)
        event = self.store.list("feedback", "task")[0]
        assessment = {"action": "replan", "answer": "New scope", "reason": "Missing requirement", "references": "spec.md"}
        with patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=json.dumps(assessment))), \
             patch.object(main, "save_state"), patch.object(main, "email"):
            main._apply_received_feedback(self.state, self.store, event)
        self.assertEqual(self.state["state"], "REPLANNING")
        self.assertNotIn("approved_proposal", self.state)
        lateral.sync_inputs(self.store, self.state, self.repo)
        self.assertEqual(self.store.list("conversation_input", "task")[0]["status"], "waiting_approval")

    def test_controller_does_not_fallback_to_chat_after_technical_failure(self):
        row = self.classify("retry", "answer")
        with patch.object(main, "_dispatch_wait_reply", side_effect=ConnectionError("offline")):
            with self.assertRaises(ConnectionError):
                main._dispatch_conversation(self.state)
        self.assertEqual(self.store.get("conversation", row["id"])["data"]["route"], "flow")

    def test_pending_change_blocks_merge_before_github_action(self):
        self.state.update(state="WAIT_MERGE", pr_url="https://github.com/org/repo/pull/1")
        row = self.classify("Add X", "change_request", [{"kind": "change", "text": "Add X"}])
        lateral.register_inputs(self.store, row, self.repo)
        with patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output='{"action":"merge"}')), \
             patch.object(main, "_receive_feedback", return_value=False), patch.object(main, "email"), \
             patch.object(main, "_pr_merge_state") as github:
            main.do_merge_reply(self.state, "merge")
        github.assert_not_called()

    def test_shutdown_stops_lateral_worker_without_mutating_task(self):
        before = copy.deepcopy(self.state)
        worker = lateral.Worker(lambda: self.store, self.repo, Mock(), Mock())
        with patch.object(main.turn_control, "request_kick") as kick:
            worker.close()
        self.assertTrue(worker.stop.is_set())
        kick.assert_called_once_with("conversation")
        self.assertEqual(self.state, before)

    def test_conversation_requires_no_configuration_flag(self):
        self.assertFalse(hasattr(main.config, "PARALLEL_CONVERSATION"))
        with patch.object(main.gmail_client, "mark_processed"):
            self.assertTrue(main._queue_conversation(self.state, "always-on", "/btw Explain"))
        rows = self.store.list("conversation", "task", identity="always-on")
        self.assertEqual(len(rows), 1)
