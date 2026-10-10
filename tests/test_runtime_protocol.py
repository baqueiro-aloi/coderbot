"""Exercise the managed bridge contract through Node, not source-text matching."""
import json
from pathlib import Path
import subprocess
import unittest


class RuntimeProtocolTests(unittest.TestCase):
    def test_async_turn_waits_past_five_minutes_and_returns_only_current_messages(self):
        root = Path(__file__).resolve().parent.parent
        script = """
import {runAsyncTurn} from './agent-plugin/runtime/async-turn.js';
const old = {info:{id:'old',role:'assistant',time:{completed:1},finish:'stop'},parts:[]};
const tools = {info:{id:'tools',role:'assistant',time:{completed:2},finish:'tool-calls'},parts:[]};
const final = {info:{id:'final',role:'assistant',time:{completed:3},finish:'stop'},parts:[{type:'text',text:'done'}]};
let elapsed=0, submitted=0, statuses=0;
const request = async (route, method='GET', body) => {
 if(method==='POST') {
  if(!route.endsWith('/prompt_async') || body.parts[0].text!=='work') throw Error('synchronous POST');
  submitted++; return {};
 }
 if(route==='/session/status') {statuses++; return {json:async()=>elapsed>300000?{}:{root:{type:elapsed===0?'idle':'busy'}}};}
 return {json:async()=>submitted ? [old,tools,...(elapsed>301000?[final]:[])] : [old]};
};
const result = await runAsyncTurn(request,'root',{parts:[{type:'text',text:'work'}]},
 {sleep:async ms=>{elapsed+=ms;}});
console.log(JSON.stringify({elapsed,submitted,statuses,ids:result.map(m=>m.info.id)}));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=10, check=True)
        value = json.loads(result.stdout)
        self.assertGreater(value["elapsed"], 300000)
        self.assertEqual(value["submitted"], 1)
        self.assertEqual(value["ids"], ["tools", "final"])

    def test_async_turn_reports_session_errors_instead_of_waiting_forever(self):
        root = Path(__file__).resolve().parent.parent
        script = """
import {runAsyncTurn} from './agent-plugin/runtime/async-turn.js';
let posted=false;
const request=async(route,method='GET')=>{
 if(method==='POST'){posted=true;return {};}
 return {json:async()=>route==='/session/status'?{}:posted?
  [{info:{id:'error',role:'assistant',error:{message:'provider failed'}},parts:[]}]:[]};
};
try {await runAsyncTurn(request,'root',{});process.exitCode=1;}
catch(e){console.log(e.message);}
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=10, check=True)
        self.assertIn("provider failed", result.stdout)

    def test_authenticated_policy_preserves_server_auth(self):
        root = Path(__file__).resolve().parent.parent
        script = """
import {trustedSessionPolicy} from './agent-plugin/runtime/protocol.js';
process.env.OPENCODE_SERVER_PASSWORD = 'fixture';
let header;
const policy = trustedSessionPolicy({serverUrl: 'http://localhost', directory: '/scratch',
 fetch: async (_, options) => {header = options.headers.authorization; return {ok:true};}});
await policy.prepare('ses_fixture');
console.log(header);
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=10, check=True)
        import base64
        self.assertEqual(result.stdout.strip(), "Basic " + base64.b64encode(b"opencode:fixture").decode())
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
