import time
import unittest
from unittest.mock import patch
import main


class ReviewDeadlineTests(unittest.TestCase):
    def test_question_continuation_preserves_thread_resolution_output(self):
        from types import SimpleNamespace
        state = {"state": "WAIT_REPLY"}
        with patch.object(main, "_scrub_evidence_from_repo", return_value=True), \
             patch.object(main, "_queue_push") as queue:
            main._continue_address_pr_threads(state, SimpleNamespace(output="RESOLVE: thread fixed"))
        self.assertEqual(queue.call_args.args[2], "RESOLVE: thread fixed")
    def test_timeout_applies_before_unavailable_thread_query(self):
        state = {"pr_url": "url", "review_since": time.time() - 10000}
        with patch.object(main, "finalize_pr") as finalize, patch.object(main, "code_review_check") as query:
            main.handle_review_wait(state)
        finalize.assert_called_once()
        query.assert_not_called()
