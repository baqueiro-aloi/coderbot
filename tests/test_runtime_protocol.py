"""Exercise the managed bridge contract through Node, not source-text matching."""
import json
from pathlib import Path
import subprocess
import unittest


class RuntimeProtocolTests(unittest.TestCase):
    def test_policy_prepares_resumed_and_child_sessions_and_answers_permissions(self):
        root = Path(__file__).resolve().parent.parent
        script = """
import {trustedSessionPolicy} from './agent-plugin/runtime/protocol.js';
const calls = [];
const policy = trustedSessionPolicy({serverUrl: 'http://localhost:1234', directory: '/scratch',
  fetch: async (url, options) => {calls.push({path: url.pathname, method: options.method,
    body: JSON.parse(options.body)}); return {ok: true};}});
await policy.before({sessionID: 'ses_resumed'});
await policy.before({sessionID: 'ses_resumed'});
await policy.event({event: {type: 'session.created', properties: {info: {id: 'ses_child'}}}});
await policy.event({event: {type: 'permission.asked', properties: {
 id: 'per_child', sessionID: 'ses_child', permission: 'external_directory'}}});
console.log(JSON.stringify(calls));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=10, check=True)
        calls = json.loads(result.stdout)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["path"], "/session/ses_resumed")
        self.assertEqual(calls[1]["body"]["permission"][-1]["action"], "allow")
        self.assertEqual(calls[2]["path"], "/session/ses_child/permissions/per_child")
        self.assertEqual(calls[2]["body"], {"response": "always"})

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
