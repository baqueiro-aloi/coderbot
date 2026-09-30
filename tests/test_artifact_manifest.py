from pathlib import Path
import tempfile
import unittest
from artifact_manifest import load, write


class ManifestTests(unittest.TestCase):
    def test_modified_or_failed_artifacts_are_not_approved_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "demo.webm"
            file.write_bytes(b"video")
            manifest = Path(root) / "manifest.json"
            write(manifest, run_id="run", snapshot="content", status="pass",
                  artifacts=[{"path": str(file), "kind": "playwright", "test_id": "demo"}])
            self.assertEqual(len(load(manifest, snapshot="content")), 1)
            file.write_bytes(b"changed")
            self.assertEqual(load(manifest), [])
            write(manifest, run_id="run", snapshot="content", status="fail", artifacts=[{"path": str(file)}])
            self.assertEqual(load(manifest), [])
