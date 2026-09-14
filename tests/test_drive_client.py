"""Drive evidence upload: folder resolution, sharing, and best-effort failure modes.

The Google client libs are stubbed; the Drive service is a MagicMock whose call
chains are inspected."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

with patch.dict(sys.modules, {"googleapiclient": MagicMock(),
                              "googleapiclient.discovery": MagicMock(),
                              "googleapiclient.errors": MagicMock(),
                              "googleapiclient.http": MagicMock(),
                              "google_auth": MagicMock()}):
    import drive_client

import config

LINK = "https://drive.google.com/file/d/f1/view"


class DriveClientTests(unittest.TestCase):
    def setUp(self):
        drive_client.reset_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "evidence.mp4"
        self.video.write_bytes(b"\x00" * 16)
        self.service = MagicMock()
        self.files = self.service.files.return_value
        self.files.create.return_value.execute.return_value = {"id": "f1", "webViewLink": LINK}
        self.files.list.return_value.execute.return_value = {"files": []}
        patches = [
            patch.object(drive_client, "_drive_service", return_value=self.service),
            patch.object(config, "DRIVE_FOLDER_ID", ""),
            patch.object(config, "DRIVE_FOLDER_NAME", "Codebot evidence"),
            patch.dict(sys.modules, {"googleapiclient": MagicMock(),
                                     "googleapiclient.errors": MagicMock(),
                                     "googleapiclient.http": MagicMock()}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _create_bodies(self):
        return [c.kwargs.get("body") for c in self.files.create.call_args_list]

    def test_explicit_folder_skips_lookup_and_shares_by_link(self):
        with patch.object(config, "DRIVE_FOLDER_ID", "folder-42"):
            link = drive_client.upload_evidence(self.video, "task-1.mp4")

        self.assertEqual(link, LINK)
        self.files.list.assert_not_called()
        body = self.files.create.call_args.kwargs["body"]
        self.assertEqual(body, {"name": "task-1.mp4", "parents": ["folder-42"]})
        perm = self.service.permissions.return_value.create
        perm.assert_called_once()
        self.assertEqual(perm.call_args.kwargs["fileId"], "f1")
        self.assertEqual(perm.call_args.kwargs["body"], {"type": "anyone", "role": "reader"})

    def test_auto_folder_is_created_once_and_cached(self):
        self.files.create.return_value.execute.side_effect = [
            {"id": "folder-new"},                       # folder creation
            {"id": "f1", "webViewLink": LINK},          # first upload
            {"id": "f2", "webViewLink": LINK + "2"},    # second upload
        ]
        first = drive_client.upload_evidence(self.video, "a.mp4")
        second = drive_client.upload_evidence(self.video, "b.mp4")

        self.assertEqual((first, second), (LINK, LINK + "2"))
        self.files.list.assert_called_once()
        query = self.files.list.call_args.kwargs["q"]
        self.assertIn("name = 'Codebot evidence'", query)
        self.assertIn("'root' in parents", query)
        bodies = self._create_bodies()
        self.assertEqual(bodies[0], {"name": "Codebot evidence",
                                     "mimeType": "application/vnd.google-apps.folder"})
        self.assertEqual(bodies[1]["parents"], ["folder-new"])
        self.assertEqual(bodies[2]["parents"], ["folder-new"])

    def test_existing_auto_folder_is_reused(self):
        self.files.list.return_value.execute.return_value = {"files": [{"id": "folder-old"}]}
        link = drive_client.upload_evidence(self.video, "a.mp4")

        self.assertEqual(link, LINK)
        self.assertEqual(self._create_bodies(), [{"name": "a.mp4", "parents": ["folder-old"]}])

    def test_folder_name_quotes_are_escaped_in_query(self):
        with patch.object(config, "DRIVE_FOLDER_NAME", "Bot's clips"):
            drive_client.upload_evidence(self.video, "a.mp4")
        self.assertIn("name = 'Bot\\'s clips'", self.files.list.call_args.kwargs["q"])

    def test_upload_failure_returns_none_and_clears_cache(self):
        self.files.list.return_value.execute.return_value = {"files": [{"id": "folder-old"}]}
        self.files.create.return_value.execute.side_effect = RuntimeError("boom")

        self.assertIsNone(drive_client.upload_evidence(self.video, "a.mp4"))
        self.assertIsNone(drive_client._folder_cache)
        self.service.permissions.return_value.create.assert_not_called()

    def test_sharing_failure_still_returns_link(self):
        self.service.permissions.return_value.create.return_value.execute.side_effect = \
            RuntimeError("policy forbids link sharing")
        with patch.object(config, "DRIVE_FOLDER_ID", "folder-42"):
            self.assertEqual(drive_client.upload_evidence(self.video, "a.mp4"), LINK)

    def test_missing_or_empty_file_makes_no_api_call(self):
        self.video.write_bytes(b"")
        self.assertIsNone(drive_client.upload_evidence(self.video, "a.mp4"))
        self.assertIsNone(drive_client.upload_evidence(Path(self.tmp.name) / "nope.mp4", "a.mp4"))
        self.service.files.assert_not_called()


if __name__ == "__main__":
    unittest.main()
