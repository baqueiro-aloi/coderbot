"""Exercise the managed bridge contract through Node, not source-text matching."""
import json
from pathlib import Path
import subprocess
import unittest


class RuntimeProtocolTests(unittest.TestCase):
    def test_child_permission_contract_matches_pinned_runtime(self):
        root = Path(__file__).resolve().parent.parent
        script = """
import {permissionRequest, RUNTIME_VERSION} from './agent-plugin/runtime/protocol.js';
import fs from 'node:fs';
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/runtime/permission-stall.json'));
const replies = fixture.events.map(permissionRequest).filter(Boolean);
console.log(JSON.stringify({version: RUNTIME_VERSION, replies}));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=10, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["version"], "1.18.18")
        self.assertEqual(data["replies"], [{"sessionID": "ses_fixture_child",
            "permissionID": "per_fixture", "response": "always"}])
