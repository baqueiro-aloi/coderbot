"""Decision cards, recorded check outcomes and evidence/feedback handoffs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
import json
from types import SimpleNamespace

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main
import handoffs


class HumanHandoffs(unittest.TestCase):
    def test_binary_selection_is_bound_to_active_task_and_phase(self):
        state = {"state": "WAIT_REPLY", "return_state": "VERIFYING", "slug": "task",
                 "verification_blocker": {"kind": "unfinished or unclassified tasks"}}
        card = handoffs.remember_decision(state, "Verification blocked")
        self.assertIn("Do you authorize", card)
        self.assertIn("1. Yes", card)
        self.assertIn("2. No", card)
        self.assertIn("Recommended", card)
        self.assertIn("approved spec", handoffs.selected_reply(state, "Sí")["reply"])
        self.assertTrue(handoffs.selected_reply(state, "NO")["wait"])
        self.assertIsNone(handoffs.selected_reply(state, "yes, but change the scope"))
        reloaded = json.loads(json.dumps(state))
        self.assertIn("explicitly authorize", handoffs.selected_reply(reloaded, "1")["reply"])
        reloaded["return_state"] = "PROPOSING"
        self.assertIsNone(handoffs.selected_reply(reloaded, "1"))
        reloaded = dict(state, slug="other")
        self.assertIsNone(handoffs.selected_reply(reloaded, "1"))

    def test_all_controller_decisions_have_feasible_choices(self):
        phases = ["proposal for review", "revised proposal", "PR ready for review", "PR updated",
                  "merge blocked", "merge failed — needs your help", "stuck in VERIFYING",
                  "e2e suite stuck — needs your help", "OpenSpec archival stuck - needs your help",
                  "blocked: dirty working tree", "service unavailable", "content blocked"]
        for phase in phases:
            with self.subTest(phase=phase):
                value = handoffs.decision({"state": "WAIT_STUCK"}, phase)
                self.assertIsNotNone(value)
                self.assertIn(len(value["options"]), (2, 3, 4))
                self.assertTrue(any(option["wait"] for option in value["options"]))
                self.assertTrue(all(option["reply"] not in ("abort", "complete") for option in value["options"]))

    def test_numeric_alternative_requires_details_and_never_treats_yes_as_merge(self):
        state = {"state": "WAIT_MERGE", "slug": "task"}
        handoffs.remember_decision(state, "PR ready for review")
        self.assertIn("error", handoffs.selected_reply(state, "yes"))
        self.assertIn("error", handoffs.selected_reply(state, "1"))
        self.assertIn("Add cancellation", handoffs.selected_reply(state, "1: Add cancellation")["reply"])
        self.assertEqual(handoffs.selected_reply(state, "2")["reply"], "merge")
        self.assertTrue(handoffs.selected_reply(state, "3")["wait"])
        self.assertIn("error", handoffs.selected_reply(state, "4"))

    def test_agent_domain_options_and_fallback_remain_readable(self):
        state = {"state": "IMPLEMENTING", "slug": "task"}
        question = "Which storage boundary?\n1. Separate DB (Recommended) — adds cost\n2. Shared DB — reduces isolation\n3. Keep waiting"
        card = handoffs.remember_decision(state, "question during IMPLEMENTING", question)
        self.assertEqual(card.count("1. Separate DB"), 1)
        state.update(state="WAIT_REPLY", return_state="IMPLEMENTING")
        self.assertIn("Separate DB", handoffs.selected_reply(state, "1")["reply"])
        self.assertTrue(handoffs.selected_reply(state, "3")["wait"])
        fallback = handoffs.remember_decision(state, "question during IMPLEMENTING", "Which customer owns the data?")
        self.assertIn("include the requested information", fallback)
        self.assertIn("error", handoffs.selected_reply(state, "1"))

    def test_selection_routes_to_existing_handler_without_feedback_investigation(self):
        state = {"state": "WAIT_REPLY", "return_state": "VERIFYING", "slug": "task",
                 "execution_task_id": "durable", "verification_blocker": {"kind": "unfinished or unclassified tasks"}}
        handoffs.remember_decision(state, "Verification blocked")
        with patch.object(main, "_handle_reply") as handle, patch.object(main.feedback, "receive") as feedback:
            main._dispatch_wait_reply(state, "msg", "sí")
        handle.assert_called_once()
        self.assertIn("explicitly authorize", handle.call_args.args[1])
        feedback.assert_not_called()
        with patch.object(main, "_handle_reply") as handle, patch.object(main, "email") as send:
            main._dispatch_wait_reply(state, "msg2", "no")
        handle.assert_not_called()
        send.assert_called_once()
        self.assertEqual(state["state"], "WAIT_REPLY")

    def test_decision_stays_visible_with_reports_in_both_channels(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel):
                state = {"state": "WAIT_REPLY", "return_state": "VERIFYING", "slug": "task", "item": "task",
                         "verification_blocker": {"kind": "unfinished or unclassified tasks"}}
                with patch.object(main.config, "COMM_CHANNEL", channel), \
                     patch.object(main.diagnostics, "report", return_value=Path("details.txt")), \
                     patch.object(main.gmail_client, "deliver", return_value={"thread_id": "thread"}) as deliver, \
                     patch.object(main, "trail"), patch.object(main, "_note_contact"):
                    main.email(state, "Verification blocked", "Traceback (most recent call last):\n" + "frame\n" * 50)
                body = deliver.call_args.args[2]
                self.assertIn("Do you authorize", body)
                self.assertIn("1. Yes", body)
                self.assertIn("2. No", body)
                self.assertIn("Reply Yes/No", body)

    def test_yes_to_pending_approved_work_reaches_implementation_transition(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] Complete approved implementation\n")
            state = {"state": "WAIT_REPLY", "return_state": "VERIFYING", "slug": "task", "item": "task",
                     "session_id": "sid", "verification_blocker": {"kind": "unfinished or unclassified tasks"},
                     "approved_task_inventory": ["Complete approved implementation"]}
            handoffs.remember_decision(state, "Verification blocked")
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.agent_runner, "run", return_value=SimpleNamespace(output='{"action":"resume_implementation"}')), \
                 patch.object(main.agent_runner, "resume") as resume, \
                 patch.object(main, "save_state"), patch.object(main, "trail"):
                main._dispatch_wait_reply(state, "message", "Sí")
            self.assertEqual(state["state"], "IMPLEMENTING")
            resume.assert_not_called()
            self.assertEqual(path.read_text(), "- [ ] Complete approved implementation\n")
            self.assertIsNone(handoffs.selected_reply(state, "Sí"))

    def test_cards_name_decision_without_changing_reply_rules(self):
        self.assertIn("approve", handoffs.decision_card({}, "proposal for review"))
        self.assertIn("answer", handoffs.decision_card({}, "question during EXPLORING"))
        self.assertIn("retry", handoffs.decision_card({}, "verification stuck"))
        self.assertIn("'merge'", handoffs.decision_card({}, "PR ready for review"))
        self.assertIn("approve", handoffs.decision_card(
            {"state": "WAIT_APPROVAL"}, "clarification needed"))

    def test_checks_are_derived_from_persisted_contracts_not_presence_of_harness(self):
        state = {"quality_report": {"openspec": "pass", "commands": ["pytest: pass"],
                                    "preexisting": ["lint: same on main"]},
                 "internal_review_report": {"status": "pass"}, "has_e2e_harness": False}
        text = handoffs.verification(state)
        self.assertIn("OpenSpec: passed", text)
        self.assertIn("lint: same on main", text)
        self.assertIn("E2E: not applicable", text)
        state["has_e2e_harness"] = True
        self.assertIn("E2E: outcome unavailable", handoffs.verification(state))
        state["e2e_passed"] = True
        self.assertIn("E2E: passed", handoffs.verification(state))

    def test_evidence_index_does_not_invent_missing_files(self):
        self.assertIn("No artifact available", handoffs.evidence_index([], None))
        self.assertIn("Demo video", handoffs.evidence_index([], "https://drive.example/video"))

    def test_feedback_recap_uses_queued_request_only_after_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "report.html"
            evidence.write_text("report")
            state = {"state": "WAIT_MERGE", "slug": "example", "branch": "bot-example",
                     "item": "Create API", "pr_url": "https://github.com/a/b/pull/3"}
            with patch.object(main, "save_state"), \
                 patch.object(main.final_checks, "run", return_value={"status": "pass"}), \
                 patch.object(main, "git"), \
                 patch.object(main, "email") as send:
                main._queue_push(state, "feedback", "Added pagination and ran unit tests",
                                 [evidence], feedback="Add pagination")
                self.assertEqual(state["state"], "PUSHING")
                self.assertEqual(state["push_context"]["feedback"], "Add pagination")
                main.do_push(state)
        self.assertIn("Requested: Add pagination", send.call_args.args[2])
        self.assertIn("Changed (implementation report): Added pagination", send.call_args.args[2])
        self.assertIn("report.html", send.call_args.args[2])
        self.assertEqual(state["state"], "WAIT_MERGE")
