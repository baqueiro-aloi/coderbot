import json
from pathlib import Path
import tempfile
import unittest
from harness_contract import load


class HarnessTests(unittest.TestCase):
    def test_legacy_and_versioned_provider_plan(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(load(root))
            path = Path(root) / "e2e"
            path.mkdir()
            (path / "codebot-harness.json").write_text(json.dumps({"version": 1,
                "preparation": {"commands": [["prepare"]], "probes": [["probe"]]},
                "checks": [{"id": "claude", "argv": ["./run.sh", "--provider", "claude"], "cwd": "e2e"}]}))
            self.assertEqual(load(root)[0].argv[-1], "claude")
            self.assertIsNotNone(load(root)[0].preparation)
