"""Sanitized durable spans; telemetry must not fail a coding operation."""
from contextlib import contextmanager
import logging
import time
from execution_store import ExecutionStore
import config

log = logging.getLogger(__name__)
ALLOWED = {"phase", "kind", "label", "reason", "status", "session_id", "tokens", "check", "reused"}


def event(task_id, **metadata):
    try:
        safe = {key: value for key, value in metadata.items() if key in ALLOWED}
        return ExecutionStore(config.DATA_DIR / "execution.sqlite").put("operation", task_id=task_id,
            status="event", data={"at": time.time(), **safe})
    except Exception:
        log.warning("performance telemetry unavailable", exc_info=True)


@contextmanager
def span(task_id, kind, label):
    store = ExecutionStore(config.DATA_DIR / "execution.sqlite")
    started = time.time()
    id = store.put("operation", task_id=task_id, status="running", data={"kind": kind, "label": label, "started": started})
    status = "complete"
    try:
        yield
    except BaseException:
        status = "interrupted"
        raise
    finally:
        store.put("operation", task_id=task_id, id=id, status=status,
                  data={"kind": kind, "label": label, "started": started, "finished": time.time()})


def summarize(rows):
    intervals = sorted((r["data"]["started"], r["data"]["finished"]) for r in rows
                       if "started" in r["data"] and "finished" in r["data"])
    merged = []
    for start, finish in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(finish, merged[-1][1])
        else:
            merged.append([start, finish])
    accumulated = sum(end - start for start, end in intervals)
    wall = sum(end - start for start, end in merged)
    return {"accumulated_seconds": accumulated, "active_wall_seconds": wall,
            "overlap_seconds": accumulated - wall,
            "incomplete_operations": sum(r["status"] in ("running", "interrupted") for r in rows)}


def prune(store, before):
    # Active checkpoints and unfinished deliveries are retained indefinitely.
    with store.connection() as db:
        db.execute("DELETE FROM operation WHERE updated<? AND status IN ('event','complete')", (before,))
