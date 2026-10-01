import gzip
import os
from pathlib import Path
import tempfile
import unittest

import attachments
import diagnostics
from execution_store import ExecutionStore


class DiagnosticsTests(unittest.TestCase):
    def test_full_chain_and_redaction_survive_reopening(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            try:
                try:
                    raise ValueError("x" * 5000 + " ghp_exampleSecretToken")
                except ValueError as cause:
                    raise RuntimeError("wrapper") from cause
            except RuntimeError as error:
                path = diagnostics.report(store, {"item": "task"}, root, root,
                                          "VERIFYING", error=error)
            text = path.read_text()
            self.assertIn("x" * 5000, text)
            self.assertIn("direct cause", text)
            self.assertIn("wrapper", text)
            self.assertNotIn("ghp_exampleSecretToken", text)
            reopened = ExecutionStore(Path(root) / "db")
            self.assertEqual(len(reopened.list("incident", store.task_identity({"item": "task"}, root))), 1)

    def test_size_limits_are_lossless_for_compression_and_parts(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "report.txt"
            for data in (b"repeat" * 10000, os.urandom(30000)):
                path.write_bytes(data)
                files = attachments.prepare(attachments.describe(path, role="diagnostic"),
                                            8192, root, mime=True)
                self.assertTrue(all(attachments.encoded_size(f["size"]) <= 8192 for f in files))
                if len(files) == 1:
                    result = gzip.decompress(Path(files[0]["path"]).read_bytes())
                else:
                    result = gzip.decompress(b"".join(Path(f["path"]).read_bytes() for f in files[1:]))
                self.assertEqual(result, data)

    def test_configured_secrets_and_headers(self):
        text = "key=supersecret Authorization: Bearer bearersecret https://example?token=secret&x=1"
        result = diagnostics.redact(text, {"API_KEY": "supersecret"})
        for secret in ("supersecret", "bearersecret", "token=secret"):
            self.assertNotIn(secret, result)
