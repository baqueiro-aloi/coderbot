"""The per-task agent log: accumulated by handle_result, archived with the change."""
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main

main.config.STATE_PATH = pathlib.Path(tempfile.mkdtemp()) / "state.json"


def result(output, question=None, attachments=()):
    return SimpleNamespace(session_id="session-1", output=output,
                           question=question, attachments=list(attachments))


class AgentLogTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        patcher = patch.object(main, "TRANSCRIPT_DIR", self.dir / "transcripts")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = {"slug": "add-widget", "branch": "codebot-a-add-widget",
                      "item": "Add a widget"}

    def log_text(self) -> str:
        return main._transcript_path(self.state).read_text()

    def test_one_file_per_task_accumulates_every_turn(self):
        main.handle_result(self.state, result("explored the code"), "EXPLORING")
        main.handle_result(self.state, result("wrote the proposal"), "PROPOSING")

        files = list((self.dir / "transcripts").iterdir())
        self.assertEqual([f.name for f in files], ["codebot-a-add-widget.md"])
        text = self.log_text()
        self.assertEqual(text.count("# Agent log — add-widget"), 1)  # header written once
        self.assertIn("Add a widget", text)
        self.assertIn("## EXPLORING", text)
        self.assertIn("explored the code", text)
        self.assertIn("## PROPOSING", text)
        self.assertIn("wrote the proposal", text)
        self.assertLess(text.index("explored the code"), text.index("wrote the proposal"))

    def test_separate_tasks_do_not_share_a_file(self):
        main.handle_result(self.state, result("first task"), "EXPLORING")
        other = dict(self.state, branch="codebot-b-other", slug="other")
        main.handle_result(other, result("second task"), "EXPLORING")

        self.assertNotIn("second task", self.log_text())
        self.assertIn("second task", main._transcript_path(other).read_text())

    def test_question_and_escalation_are_annotated(self):
        main.handle_result(self.state, result("body", question="which color?"), "IMPLEMENTING")
        self.assertIn("waiting for a reply", self.log_text())

        self.state["question_rounds"] = main.config.QUESTION_MAX_ROUNDS
        main.handle_result(self.state, result("body", question="still?"), "IMPLEMENTING")
        self.assertIn("escalated to WAIT_STUCK", self.log_text())

    def test_write_failure_never_breaks_the_phase(self):
        with patch.object(main, "_transcript_path", side_effect=OSError("no space")):
            self.assertFalse(main.handle_result(self.state, result("body"), "EXPLORING"))

    def test_archive_copies_the_log_into_the_change(self):
        main.handle_result(self.state, result("did the work"), "IMPLEMENTING")
        target = self.dir / "2026-09-08-add-widget"
        target.mkdir()

        main._archive_transcript(self.state, target)

        self.assertIn("did the work", (target / "agent-log.md").read_text())

    def test_archive_without_a_log_is_a_no_op(self):
        target = self.dir / "2026-09-08-add-widget"
        target.mkdir()

        main._archive_transcript(self.state, target)

        self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
