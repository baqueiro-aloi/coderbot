import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main
import feedback
import replanning
import verification_ledger
import review_intent
from execution_store import ExecutionStore


class FeedbackRecoveryTests(unittest.TestCase):
    def test_dropdown_feedback_replans_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            database = ExecutionStore(Path(root) / "db")
            state = {"item": "models", "state": "ADDRESS_PR_THREADS", "slug": "models",
                     "session_id": "session", "branch": "feature", "pr_url": "https://example/pr/1"}
            message = "No veo un drop down donde se pueda elegir el modelo. Eso está implementado? Eso es parte de feature"
            feedback.receive(database, state, root, "message1", message)
            value = {"action": "replan", "answer": "The selector is missing.",
                     "reason": "Session/provider design must change.", "references": "design.md; toolbar.tsx"}
            with patch.object(main.phase_checkpoint, "store", return_value=database), \
                 patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=json.dumps(value))), \
                 patch.object(main, "email"):
                self.assertTrue(main._dispatch_feedback(state))
            self.assertEqual(state["state"], "REPLANNING")
            self.assertEqual(state["replan"]["feedback"], message)
            self.assertEqual(state["pr_url"], "https://example/pr/1")
            restored = json.loads(json.dumps(state))
            self.assertEqual(restored["replan"], state["replan"])
            self.assertEqual(database.list("feedback", database.task_identity(state, root))[0]["status"], "planning")

    def test_complementary_replan_preserves_archive_and_pr(self):
        state = {"state": "WAIT_MERGE", "slug": "models", "archive_path": "openspec/changes/archive/old",
                 "pr_url": "https://example/pr/1", "approved_proposal": "old"}
        row = {"id": "message1", "data": {"text": "Need a selector", "assessment": {}}}
        replanning.begin(state, row)
        prompt = replanning.prompt(state, Path("/repo"))
        self.assertIn("openspec new change", prompt)
        self.assertIn("do not rewrite", prompt)
        self.assertEqual(state["replan"]["original_archive"], "openspec/changes/archive/old")
        self.assertNotIn("approved_proposal", state)

    def test_coverage_and_review_provenance(self):
        inventory = [{"id": "model", "title": "Model selector"}, {"id": "effort", "title": "Effort"}]
        report = {"snapshot": "head", "requirements": [{"id": "effort", "status": "implemented",
                   "implementation": "toolbar", "verification": "tests"}]}
        self.assertEqual(verification_ledger.validate_coverage(inventory, report, "head"), ["Model selector"])
        self.assertEqual(review_intent.provenance({"author": "pr-code-review-aloi", "body": "ai-review-inline"}), "automated")
        self.assertEqual(review_intent.provenance({"author": "unknown"}), "unknown")

    def test_transient_review_failure_does_not_consume_round(self):
        state = {"item": "models", "state": "ADDRESS_PR_THREADS", "session_id": "session", "branch": "feature",
                 "pr_threads": [], "pr_thread_round": 2}
        with patch.object(main.agent_runner, "resume", side_effect=ConnectionError("fetch failed")), \
             patch.object(main, "_render_review_threads", return_value="threads"):
            with self.assertRaises(ConnectionError):
                main.do_address_pr_threads(state)
        self.assertEqual(state["pr_thread_round"], 2)

    def test_recovery_question_preserves_original_blocker(self):
        state = {"item": "task", "state": "WAIT_STUCK", "stuck_return": "RECOVERING",
                 "stuck_error": "dirty index", "session_id": "session", "recovery_id": "incident"}
        result = SimpleNamespace(session_id="session2", output="Question", question="Which behavior?", attachments=[])
        with patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output='{"action":"instructions"}')), \
             patch.object(main.agent_runner, "resume", return_value=result), \
             patch.object(main, "email"), patch.object(main, "trail"):
            main.do_stuck_reply(state, "Inspect the change")
        self.assertEqual(state["state"], "WAIT_REPLY")
        self.assertEqual(state["return_state"], "RECOVERING")
        self.assertEqual(state["recovery_id"], "incident")
        self.assertEqual(state["stuck_error"], "dirty index")

    def test_revised_proposal_edits_never_undo_implementation(self):
        state = {"item": "task", "state": "WAIT_APPROVAL", "slug": "revision",
                 "session_id": "session", "replan": {"feedback": "selector"}}
        with patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output='{"action":"changes","feedback":"revise"}')), \
             patch.object(main.agent_runner, "resume", return_value=SimpleNamespace(session_id="session", output="revised", question=None)), \
             patch.object(main, "_send_proposal_review"), patch.object(main, "_undo_premature_work") as undo, \
             patch.object(main, "handle_result", return_value=False):
            main.do_approval_reply(state, "Revise the API behavior")
        undo.assert_not_called()

    def test_missing_requirement_blocks_delivery_before_evidence_work(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"item": "task", "state": "OPEN_PR", "slug": "models", "session_id": "session",
                     "approved_proposal": "approved", "pr_url": "https://example/pr/1"}
            inventory = [{"id": "selector", "title": "Model selector", "spec": "spec.md"}]
            output = {"requirements": [{"id": "selector", "title": "Model selector", "status": "missing",
                       "implementation": "", "verification": ""}]}
            with patch.object(main.phase_checkpoint, "store", return_value=store), \
                 patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "content_snapshot", return_value="head"), \
                 patch.object(main.verification_ledger, "requirements", return_value=inventory), \
                 patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=json.dumps(output))), \
                 patch.object(main, "save_state"), patch.object(main.evidence, "record_evidence") as record:
                main.finalize_pr(state)
            self.assertEqual(state["state"], "REPLANNING")
            record.assert_not_called()

    def test_stale_merge_cannot_bypass_revision(self):
        state = {"item": "task", "state": "WAIT_MERGE", "replan": {"feedback": "selector"},
                 "pr_url": "https://example/pr/1"}
        with patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output='{"action":"merge","force":true}')), \
             patch.object(main, "email") as notify, patch.object(main, "_pr_merge_state") as merge:
            main.do_merge_reply(state, "merge anyway")
        merge.assert_not_called()
        self.assertIn("requires approval", notify.call_args.args[2])

    def test_failed_feedback_delivery_keeps_pending_record(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            state = {"item": "task", "state": "ADDRESS_PR_THREADS", "slug": "task"}
            feedback.receive(store, state, root, "m1", "Where is the selector?")
            value = {"action": "answer", "answer": "It is in the toolbar.", "reason": "Implemented.", "references": "toolbar.tsx"}
            with patch.object(main.phase_checkpoint, "store", return_value=store), \
                 patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output=json.dumps(value))), \
                 patch.object(main, "email", side_effect=ConnectionError("offline")):
                with self.assertRaises(ConnectionError):
                    main._dispatch_feedback(state)
            self.assertEqual(len(feedback.pending(store, state, root)), 1)
            self.assertFalse(feedback.pending(store, state, root)[0]["data"].get("assessment_delivered"))

    def test_active_turn_receipt_is_durable_and_keeps_control_commands(self):
        with tempfile.TemporaryDirectory() as root:
            database = ExecutionStore(Path(root) / "db")
            state = {"item": "task", "state": "IMPLEMENTING", "thread_id": "C:1"}
            with patch.object(main.phase_checkpoint, "store", return_value=database), \
                 patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.gmail_client, "poll_reply", return_value=("m1", "Missing selector")), \
                 patch.object(main.gmail_client, "foreign_command", return_value=None), \
                 patch.object(main.gmail_client, "send") as ack, \
                 patch.object(main.gmail_client, "mark_processed") as processed:
                main._receive_feedback(state)
                main._receive_feedback(state)
            self.assertEqual(len(feedback.pending(database, state, root)), 1)
            ack.assert_called_once()
            with patch.object(main.gmail_client, "poll_reply", return_value=("m2", "ABORT")), \
                 patch.object(main.gmail_client, "mark_processed") as processed:
                self.assertFalse(main._receive_feedback(state))
                processed.assert_not_called()
