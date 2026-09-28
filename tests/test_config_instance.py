"""Instance identity: sanitized explicit names, generated-and-persisted ids."""
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class InstanceId(unittest.TestCase):
    def test_module_id_is_sane_and_prefixes_subjects(self):
        self.assertRegex(config.INSTANCE_ID, r"^[a-z0-9-]+$")
        self.assertEqual(config.SUBJECT_PREFIX, f"[{config.INSTANCE_ID}]")

    def test_explicit_name_is_sanitized(self):
        with patch.dict(os.environ, {"CODEBOT_INSTANCE": "@East!"}):
            self.assertEqual(config._instance_id(), "east")
        with patch.dict(os.environ, {"CODEBOT_INSTANCE": "東京"}):
            self.assertEqual(config._instance_id(), "codebot")
        with patch.dict(os.environ, {"CODEBOT_INSTANCE": "--Bot--A__1--"}):
            self.assertEqual(config._instance_id(), "bot-a-1")

    def test_generated_id_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"CODEBOT_INSTANCE": ""}), \
                patch.object(config, "DATA_DIR", Path(tmp)):
            first = config._instance_id()
            self.assertRegex(first, r"^codebot-[a-z]+-[a-z]+$")
            self.assertEqual((Path(tmp) / "instance_id").read_text().strip(), first)
            self.assertEqual(config._instance_id(), first)

    def test_corrupt_saved_id_is_regenerated(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"CODEBOT_INSTANCE": ""}), \
                patch.object(config, "DATA_DIR", Path(tmp)):
            (Path(tmp) / "instance_id").write_text("Bad Name!\n")
            self.assertRegex(config._instance_id(), r"^codebot-[a-z]+-[a-z]+$")

    def test_existing_generated_id_keeps_ownership_after_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"CODEBOT_INSTANCE": ""}), \
                patch.object(config, "DATA_DIR", Path(tmp)):
            (Path(tmp) / "instance_id").write_text("codebot-x7k2\n")
            self.assertEqual(config._instance_id(), "codebot-x7k2")

    def test_warty_warthog_is_a_valid_generated_pair(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"CODEBOT_INSTANCE": ""}), \
                patch.object(config, "DATA_DIR", Path(tmp)), \
                patch.object(config.secrets, "choice", side_effect=["warty", "warthog"]):
            self.assertEqual(config._instance_id(), "codebot-warty-warthog")

    def test_fingerprint_persists_and_separates_identical_names(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with patch.object(config, "DATA_DIR", Path(a)):
                first = config._instance_fingerprint()
                self.assertEqual(config._instance_fingerprint(), first)
                self.assertRegex(first, r"^[0-9a-f]{32}$")
            with patch.object(config, "DATA_DIR", Path(b)):
                self.assertNotEqual(config._instance_fingerprint(), first)


if __name__ == "__main__":
    unittest.main()
