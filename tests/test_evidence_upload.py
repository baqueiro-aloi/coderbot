"""Evidence video offload: the stitched mp4 goes to Drive and the emails link to it
(the link rides the body so the activity trail mirrors it); anything that is not an
mp4, or whose upload failed, is attached as before."""
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main

main.config.STATE_PATH = pathlib.Path(tempfile.mkdtemp()) / "state.json"

LINK = "https://drive.google.com/file/d/abc/view"
MP4 = Path("/tmp/evidence.mp4")


class OffloadHelperTests(unittest.TestCase):
    def setUp(self):
        self.state = {"slug": "api-version", "branch": "codebot-api-version"}
        p = patch.object(main.config, "EVIDENCE_UPLOAD", True)
        p.start()
        self.addCleanup(p.stop)

    def test_uploads_only_mp4_and_drops_it_from_attachments(self):
        with patch.object(main.drive_client, "upload_evidence", return_value=LINK) as upload:
            remaining, text = main._offload_evidence_video(
                self.state, [Path("/tmp/report.html"), MP4, Path("/tmp/shot.png")])

        self.assertEqual(remaining, [Path("/tmp/report.html"), Path("/tmp/shot.png")])
        self.assertEqual(text, LINK)
        self.assertEqual(self.state["evidence_url"], LINK)
        upload.assert_called_once()
        path, name = upload.call_args.args
        self.assertEqual(path, MP4)
        self.assertRegex(name, r"^codebot-api-version-\d{8}-\d{6}\.mp4$")

    def test_failed_upload_keeps_mp4_attached(self):
        with patch.object(main.drive_client, "upload_evidence", return_value=None):
            remaining, text = main._offload_evidence_video(self.state, [MP4])
        self.assertEqual(remaining, [MP4])
        self.assertIsNone(text)
        self.assertNotIn("evidence_url", self.state)

    def test_disabled_upload_is_a_no_op(self):
        with patch.object(main.config, "EVIDENCE_UPLOAD", False), \
             patch.object(main.drive_client, "upload_evidence") as upload:
            self.assertEqual(main._offload_evidence_video(self.state, [MP4]), ([MP4], None))
        upload.assert_not_called()

    def test_two_videos_get_distinct_names(self):
        with patch.object(main.drive_client, "upload_evidence",
                          side_effect=[LINK, LINK + "2"]) as upload:
            remaining, text = main._offload_evidence_video(
                self.state, [MP4, Path("/tmp/outbox/demo.mp4")])
        self.assertEqual(remaining, [])
        self.assertEqual(text, f"{LINK}\n{LINK}2")
        names = [c.args[1] for c in upload.call_args_list]
        self.assertNotEqual(names[0], names[1])
        self.assertTrue(names[1].endswith("-2.mp4"))


class FinalizePrTests(unittest.TestCase):
    def setUp(self):
        self.state = {"state": "ADDRESS_REVIEW", "slug": "api-version",
                      "branch": "codebot-api-version", "item": "Support another API version",
                      "pr_url": "https://github.com/acme/repo/pull/7", "pr_summary": "summary",
                      "e2e_kind": "playwright", "has_e2e_harness": True}
        for p in (patch.object(main.config, "EVIDENCE_UPLOAD", True),
                  patch.object(main, "unresolved_review_threads", return_value=[])):
            p.start()
            self.addCleanup(p.stop)

    def _finalize(self, evidence_files, link):
        with patch.object(main.evidence, "record_evidence", return_value=evidence_files), \
             patch.object(main.drive_client, "upload_evidence", return_value=link) as upload, \
             patch.object(main, "email") as email:
            main.finalize_pr(self.state)
        return email.call_args.args, upload

    def test_links_video_and_sends_no_attachment(self):
        args, _ = self._finalize([MP4], LINK)
        self.assertEqual(args[1], "PR ready for review")
        self.assertIn(f"Video: {LINK}", args[2])
        self.assertNotIn("Attached:", args[2])
        self.assertEqual(args[3], [])
        self.assertEqual(self.state["evidence_url"], LINK)
        self.assertEqual(self.state["state"], "WAIT_MERGE")

    def test_failed_upload_attaches_as_before(self):
        args, _ = self._finalize([MP4], None)
        self.assertIn("Attached: a Playwright video (mp4)", args[2])
        self.assertNotIn("Video:", args[2])
        self.assertEqual(args[3], [MP4])

    def test_newman_report_is_not_uploaded(self):
        self.state["e2e_kind"] = "newman"
        report = Path("/tmp/report.html")
        args, upload = self._finalize([report], LINK)
        upload.assert_not_called()
        self.assertIn("Attached: a Newman run report (html)", args[2])
        self.assertEqual(args[3], [report])

    def test_reset_keys_forget_the_link_between_tasks(self):
        self.assertIn("evidence_url", main.RESET_KEYS)


class FeedbackPushTests(unittest.TestCase):
    def test_feedback_push_links_video_and_attaches_the_rest(self):
        state = {"state": "PUSHING", "branch": "codebot-api-version", "slug": "api-version",
                 "pr_url": "https://github.com/acme/repo/pull/7",
                 "push_context": {"continuation": "feedback", "output": "fixed details",
                                  "attachments": [str(MP4), "/tmp/evidence.txt"]}}
        with patch.object(main.config, "EVIDENCE_UPLOAD", True), \
             patch.object(main, "git"), \
             patch.object(main.drive_client, "upload_evidence", return_value=LINK), \
             patch.object(main, "email") as email:
            main.do_push(state)

        args = email.call_args.args
        self.assertEqual(args[1], "PR updated")
        self.assertIn("fixed details", args[2])
        self.assertTrue(args[2].endswith(f"Video: {LINK}"))
        self.assertEqual(args[3], [Path("/tmp/evidence.txt")])
        self.assertEqual(state["state"], "WAIT_MERGE")
        self.assertNotIn("push_context", state)


if __name__ == "__main__":
    unittest.main()
