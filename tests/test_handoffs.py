"""Decision cards, recorded check outcomes and evidence/feedback handoffs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main
import handoffs


class HumanHandoffs(unittest.TestCase):
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
