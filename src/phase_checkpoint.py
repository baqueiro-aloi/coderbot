"""Replay completed agent outcomes until the surrounding FSM phase commits."""
import hashlib
import os

import config
from execution_identity import snapshot
from execution_store import ExecutionStore
from selfheal_events import runtime_epoch


def store():
    return ExecutionStore(config.DATA_DIR / "execution.sqlite")


def key(state, prompt, *, epoch=None):
    # Same phase invocation can be replayed after notification failure. A different
    # prompt (including feedback) is a new invocation even within the same phase.
    return hashlib.sha256(((runtime_epoch() if epoch is None else epoch) + "\0" + state["state"] + "\0" + prompt).encode()).hexdigest()


def _invocation_keys(state, prompt):
    keys = [key(state, prompt)]
    previous = os.environ.get("CODEBOT_PREVIOUS_RUNTIME_EPOCH")
    if previous and previous != runtime_epoch():
        keys.append(key(state, prompt, epoch=previous))
    return keys


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
    for identity in _invocation_keys(state, prompt):
        for row in db.list("checkpoint", task_id, identity=identity, status="running"):
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
    task = db.task_identity(state, config.REPO_PATH)
    # Deployment invalidates completed computational evidence, not the history
    # of the exact unfinished task/phase/prompt. Never reuse a completed old turn.
    for identity in _invocation_keys(state, prompt):
        matches = db.list("checkpoint", task, identity=identity, status="running")
        session = next((row["data"]["session_id"] for row in matches
                        if row["data"].get("agent") == config.AGENT), None)
        if session:
            return session
    return None


def retire(state, phase):
    db = store()
    task_id = db.task_identity(state, config.REPO_PATH)
    for row in db.list("checkpoint", task_id):
        if row["data"].get("phase") == phase:
            db.put("checkpoint", task_id=task_id, id=row["id"], identity=row["identity"],
                   status="consumed", data=row["data"])
