"""Replay completed agent outcomes until the surrounding FSM phase commits."""
import hashlib

import config
from execution_identity import snapshot
from execution_store import ExecutionStore


def store():
    return ExecutionStore(config.DATA_DIR / "execution.sqlite")


def key(state, prompt):
    # Same phase invocation can be replayed after notification failure. A different
    # prompt (including feedback) is a new invocation even within the same phase.
    return hashlib.sha256((state["state"] + "\0" + prompt).encode()).hexdigest()


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
    db.put("checkpoint", task_id=task_id, identity=key(state, prompt), status="complete",
           data={"session_id": result.session_id, "output": result.output,
                 "phase": state["state"], "snapshot": snapshot(config.REPO_PATH)})


def retire(state, phase):
    db = store()
    task_id = db.task_identity(state, config.REPO_PATH)
    for row in db.list("checkpoint", task_id, status="complete"):
        if row["data"].get("phase") == phase:
            db.put("checkpoint", task_id=task_id, id=row["id"], identity=row["identity"],
                   status="consumed", data=row["data"])
