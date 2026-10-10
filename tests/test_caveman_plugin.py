"""Smoke tests for the real pinned plugin; run inside the built Docker image."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path("/opt/coderbot/caveman")


@unittest.skipUnless(PLUGIN.is_dir(), "managed Caveman plugin requires Docker image")
class CavemanPluginTests(unittest.TestCase):
    def test_claude_headless_start_resume_and_subagent_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "settings.json").write_text('{"statusLine":{"command":"true"}}')
            env = dict(os.environ, CLAUDE_CONFIG_DIR=tmp, CLAUDE_PLUGIN_ROOT=str(PLUGIN),
                       CLAUDE_CODE_ENTRYPOINT="sdk-cli", CAVEMAN_DEFAULT_MODE="caveman")
            hook = str(PLUGIN / "src/hooks/caveman-activate.js")
            for source, args in (("startup", []), ("resume", []), ("startup", ["--subagent"])):
                result = subprocess.run(["node", hook, *args], env=env, cwd=tmp,
                                        input=json.dumps({"session_id": "smoke-session",
                                                          "source": source, "cwd": tmp}),
                                        capture_output=True, text=True, check=True, timeout=10)
                self.assertIn("CAVEMAN MODE ACTIVE", result.stdout)
                self.assertIn("All technical substance stay", result.stdout)
            env["CAVEMAN_DEFAULT_MODE"] = "off"
            result = subprocess.run(["node", hook], env=env, cwd=tmp,
                                    input=json.dumps({"session_id": "off-session", "source": "startup"}),
                                    capture_output=True, text=True, check=True, timeout=10)
            self.assertNotIn("CAVEMAN MODE ACTIVE", result.stdout)

    def test_opencode_load_reinforcement_subagent_and_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = r"""
import assert from 'node:assert/strict';
import {CavemanPlugin} from '/opt/coderbot/caveman/src/plugins/opencode/plugin.js';
const hooks = await CavemanPlugin({});
const transform = hooks['experimental.chat.system.transform'];
for (const sessionID of ['primary', 'resumed', 'child']) {
  const output = {system: ['Existing contract: JSON and sentinels verbatim.']};
  await transform({sessionID}, output);
  assert.match(output.system[0], /CAVEMAN MODE ACTIVE/);
  assert.match(output.system[0], /All technical substance stay/);
  await transform({sessionID}, output);
  assert.equal(output.system[0].split('CAVEMAN MODE ACTIVE').length, 2);
}
await hooks['chat.message']({}, {parts:[{type:'text', text:'/caveman off'}]});
let output = {system:['contract']};
await transform({}, output);
assert.deepEqual(output.system, ['contract']);
await hooks['chat.message']({}, {parts:[{type:'text', text:'Activate caveman mode: '}]});
output = {system:[]};
await transform({}, output);
assert.match(output.system[0], /CAVEMAN MODE ACTIVE/);
process.env.CAVEMAN_DEFAULT_MODE = 'off';
await hooks.event({event:{type:'session.created'}});
output = {system:[]};
await transform({}, output);
assert.deepEqual(output.system, []);
"""
            subprocess.run(["node", "--input-type=module", "-e", script], cwd=tmp,
                           env=dict(os.environ, XDG_CONFIG_HOME=tmp, CAVEMAN_DEFAULT_MODE="caveman"),
                           capture_output=True, text=True, check=True, timeout=10)
