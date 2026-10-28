"""Short transition explanations use controller facts, never agent success claims."""
import json
import unittest

import main
import milestones
import state_notices


class StateNotices(unittest.TestCase):
    def test_every_controller_state_has_a_short_reason_in_both_languages(self):
        phases = set(main.PHASES) | main.WAITS | set(milestones.STATE_STAGES)
        self.assertFalse(phases - state_notices.REASONS.keys())
        for phase in phases:
            for language in ("English", "Spanish"):
                with self.subTest(phase=phase, language=language):
                    reason = state_notices.reason({"state": phase, "task_language": language})
                    self.assertTrue(reason)
                    self.assertLessEqual(len(reason), 240)
                    self.assertNotIn("\n", reason)

    def test_review_findings_and_invalid_review_are_different_reasons(self):
        state = {"state": "APPLY_FEEDBACK", "pending_feedback": "Fix internal review findings:\n" +
                 'INTERNAL_REVIEW: ' + json.dumps({"status": "fail", "critical": [], "important": ["one", "two"]})}
        self.assertIn("2 issues", state_notices.reason(state))
        state["task_language"] = "Spanish"
        self.assertIn("2 problemas", state_notices.reason(state))
        state["pending_feedback"] = 'Fix internal review findings:\nINTERNAL_REVIEW: {"status":"pass","critical":[],"important":[]}'
        self.assertIn("informe", state_notices.reason(state))
        self.assertNotIn("problemas", state_notices.reason(state))

    def test_return_to_verification_does_not_claim_repairs_or_tests_passed(self):
        reason = state_notices.reason({"state": "VERIFYING", "banner_state": "APPLY_FEEDBACK",
                                       "final_check_report": {"status": "pass"}})
        self.assertIn("repair turn", reason)
        self.assertNotIn("passed", reason)

    def test_notification_never_copies_private_or_verbose_feedback(self):
        state = {"state": "IMPLEMENTING", "implementation_feedback": "SECRET=value\n" * 200,
                 "pending_feedback": "password=private"}
        self.assertNotIn("SECRET", state_notices.reason(state))
        self.assertNotIn("private", state_notices.reason(state))

    def test_unresolved_checks_are_reported_without_claiming_success(self):
        state = {"state": "REPAIR_CHECKS", "final_check_report": {"checks": [
            {"check": "one", "gate": {"status": "pass"}},
            {"check": "two", "gate": {"status": "indeterminate"}}]}}
        self.assertIn("1 unresolved check", state_notices.reason(state))

    def test_invalid_check_plan_is_not_reported_as_a_product_defect(self):
        reason = state_notices.reason({"state": "VERIFYING", "reported_check_plan_error": "private detail",
                                       "banner_state": "APPLY_FEEDBACK"})
        self.assertIn("invalid format", reason)
        self.assertNotIn("private", reason)
        self.assertNotIn("issues", reason)

    def test_optional_legacy_fields_can_be_null(self):
        for phase in ("APPLY_FEEDBACK", "REPAIR_CHECKS"):
            with self.subTest(phase=phase):
                self.assertTrue(state_notices.reason({"state": phase, "pending_feedback": None,
                                                      "task_language": None, "final_check_report": None}))
