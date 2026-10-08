"""Replay completed agent outcomes until the surrounding FSM phase commits."""
import hashlib
import json

import config
from execution_identity import snapshot
from execution_store import ExecutionStore


def store():
    return ExecutionStore(config.DATA_DIR / "execution.sqlite")


def key(state, prompt):
    # Same phase invocation can be replayed after notification failure. A different
    # prompt (including feedback) is a new invocation even within the same phase.
    policy = {name: state.get(name) for name in (
        'integration_inventory', 'validation_overrides', 'external_authorizations',
        'pending_credential_request', 'approved_task_inventory', 'verified_task_inventory',
        'reviewed_remote_sha', 'verification_guidance', 'coverage_report')}
    return hashlib.sha256((state["state"] + "\0" + prompt + '\0'
        + json.dumps(policy, sort_keys=True)).encode()).hexdigest()


def replay(state, prompt):
    db = store()
    task_id = db.task_identity(state, config.REPO_PATH)
    matches = db.list("checkpoint", task_id, identity=key(state, prompt), status="complete")
    if matches and matches[0]["data"].get("snapshot") == snapshot(config.REPO_PATH):
        return matches[0]["data"]
    return None


def record(state, prompt, result):
    db = store()
    task_id = db.task_identity(state, config.REPO_PATH)
    for row in db.list("checkpoint", task_id, identity=key(state, prompt), status="running"):
        db.update("checkpoint", row, status="consumed")
    db.put("checkpoint", task_id=task_id, identity=key(state, prompt), status="complete",
           data={"session_id": result.session_id, "output": result.output,
                  "phase": state["state"], "snapshot": snapshot(config.REPO_PATH)})


def remember_session(state, prompt, session_id):
    """Persist the invocation before completion, including its partial edits."""
    db = store()
    task_id = db.task_identity(state, config.REPO_PATH)
    rows = db.list("checkpoint", task_id, identity=key(state, prompt), status="running")
    db.put("checkpoint", task_id=task_id, id=rows[0]["id"] if rows else None,
           identity=key(state, prompt), status="running",
           data={"session_id": session_id, "phase": state["state"], "agent": config.AGENT})


def interrupted(state, prompt):
    db = store()
    matches = db.list("checkpoint", db.task_identity(state, config.REPO_PATH),
                      identity=key(state, prompt), status="running")
    return next((row["data"]["session_id"] for row in matches
                 if row["data"].get("agent") == config.AGENT), None)


def retire(state, phase):
    db = store()
    task_id = db.task_identity(state, config.REPO_PATH)
    for row in db.list("checkpoint", task_id):
        if row["data"].get("phase") == phase:
            db.put("checkpoint", task_id=task_id, id=row["id"], identity=row["identity"],
                   status="consumed", data=row["data"])
