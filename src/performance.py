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
