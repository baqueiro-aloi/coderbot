import json
from pathlib import Path
import tempfile
import unittest
from harness_contract import load


class HarnessTests(unittest.TestCase):
    def test_pica_specs_are_grouped_per_provider_not_per_file(self):
        from pica_harness import grouped
        prep = {"inputs": ["backend/requirements.txt", "e2e/package-lock.json", "e2e/Dockerfile.claude-runner"]}
        checks = grouped(["e2e/configuracion-modelo-esfuerzo.spec.ts", "a.spec.ts", "b.spec.ts"], prep)
        self.assertEqual(len(checks), 2)
        self.assertEqual(checks[0].argv, ["./run.sh", "--provider", "claude", "a.spec.ts", "b.spec.ts"])
        self.assertEqual(checks[1].argv[2], "litellm")
        self.assertEqual(checks[0].resources, checks[1].resources)
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
