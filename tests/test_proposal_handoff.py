"""All proposal handoffs share the same complete, frozen review document."""
import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main


class ProposalHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.change = self.repo / "openspec/changes/example"
        (self.change / "specs/api").mkdir(parents=True)
        for name in ("proposal.md", "design.md", "tasks.md"):
            (self.change / name).write_text(f"## {name}\nFirst\n")
        (self.change / "specs/api/spec.md").write_text("## API\nFirst\n")
        self.state = {"state": "PROPOSING", "slug": "example", "branch": "bot-example",
                      "item": "Create API"}

    def test_initial_and_revisions_send_current_complete_package(self):
        with patch.object(main.config, "REPO_PATH", self.repo), \
             patch.object(main.config, "DATA_DIR", self.root / "data"), \
             patch.object(main, "save_state"), patch.object(main, "email") as send:
            main._send_proposal_review(self.state, "Proposal summary")
            self.assertEqual(self.state["state"], "WAIT_APPROVAL")
            first = send.call_args.args[3][0]
            self.assertIn("specs/api/spec.md", first.read_text())
            self.assertTrue(Path(self.state["proposal_snapshot"]).is_file())
            (self.change / "design.md").write_text("## design.md\nSecond\n")
            main._send_proposal_review(self.state, "Revised summary", revised=True,
                                       feedback="Change design")
            second = send.call_args.args[3][0]
            self.assertNotEqual(first, second)
            self.assertIn("Changed in design.md", send.call_args.args[2])
            self.assertIn("First", first.read_text())
            self.assertIn("Second", second.read_text())
            send.reset_mock()
            main._send_proposal_review(self.state, "Revised summary", revised=True,
                                       feedback="Change design")
            send.assert_not_called()

    def test_missing_bundle_never_requests_approval(self):
        (self.change / "tasks.md").unlink()
        with patch.object(main.config, "REPO_PATH", self.repo), \
             patch.object(main.config, "DATA_DIR", self.root / "data"), \
             patch.object(main, "email") as send, \
             patch.object(main, "_enter_stuck") as stuck:
            main._send_proposal_review(self.state, "summary")
        send.assert_not_called()
        self.assertIn("complete OpenSpec review package", stuck.call_args.args[2])

    def test_direct_and_question_continuation_use_same_sender(self):
        result = SimpleNamespace(output="Summary", session_id="sid", question=None)
        with patch.object(main.agent_runner, "resume", return_value=result), \
             patch.object(main, "handle_result", return_value=False), \
             patch.object(main, "_undo_premature_work", return_value=""), \
             patch.object(main, "_send_proposal_review") as sender:
            self.state["session_id"] = "sid"
            main.do_propose(self.state)
            main._continue_proposing(self.state, result)
        self.assertEqual(sender.call_count, 2)

    def test_complete_review_package_sent_in_both_channels(self):
        for channel, thread in (("email", "gmail-1"), ("slack", "C1:1.0")):
            with self.subTest(channel=channel), \
                 patch.object(main.config, "REPO_PATH", self.repo), \
                 patch.object(main.config, "DATA_DIR", self.root / channel), \
                 patch.object(main.config, "COMM_CHANNEL", channel), \
                 patch.object(main, "save_state"), \
                  patch.object(main, "trail"), \
                  patch.object(main.gmail_client, "send", return_value=thread) as banner, \
                  patch.object(main.gmail_client, "deliver", return_value={"thread_id": thread, "complete": True}) as send:
                state = dict(self.state, thread_id=thread)
                main._send_proposal_review(state, "Summary")
                self.assertEqual(send.call_args.args[4][0].suffix, ".html")
                self.assertIn("specs/api/spec.md", send.call_args.args[4][0].read_text())
                self.assertEqual(state["state"], "WAIT_APPROVAL")
                self.assertEqual(banner.call_args.kwargs["progress"].stem, "approval")
