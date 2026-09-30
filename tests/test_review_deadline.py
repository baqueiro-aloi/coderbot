import time
import unittest
from unittest.mock import patch
import main


class ReviewDeadlineTests(unittest.TestCase):
    def test_timeout_applies_before_unavailable_thread_query(self):
        state = {"pr_url": "url", "review_since": time.time() - 10000}
        with patch.object(main, "finalize_pr") as finalize, patch.object(main, "code_review_check") as query:
            main.handle_review_wait(state)
        finalize.assert_called_once()
        query.assert_not_called()
