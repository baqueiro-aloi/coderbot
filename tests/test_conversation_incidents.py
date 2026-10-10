from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
import unittest
import sys

with patch.dict(sys.modules, {"task_source": Mock(), "gdoc_client": Mock(), "gmail_client": Mock()}):
    import main


class IncidentPresentationTests(unittest.TestCase):
    def test_traceback_is_attached_with_action_preserved(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(main.config, "DATA_DIR", Path(root)), \
             patch.object(main, "trail"), \
             patch.object(main.gmail_client, "deliver", return_value={"thread_id": "t", "complete": True}) as deliver:
            body = "Execution failed.\nTraceback (most recent call last):\n" + "frame\n" * 1000 + "Reply 'retry' to resume."
            main.email({"item": "task", "thread_id": "t"}, "failure", body)
            summary = deliver.call_args.args[2]
            files = deliver.call_args.args[4]
            self.assertNotIn("Traceback", summary)
            self.assertIn("Reply 'retry'", summary)
            self.assertIn("frame" * 1, files[0].read_text())
            self.assertGreater(len(files[0].read_text()), 5000)
            self.assertLessEqual(len(summary.splitlines()), 10)
