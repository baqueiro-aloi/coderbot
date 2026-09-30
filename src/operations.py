"""Monotonic budgets and observable operations shared by retries and tools."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
import uuid


_budget = ContextVar("operation_budget", default=None)
_lock = threading.Lock()
_active = {}


class Budget:
    def __init__(self, seconds, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + seconds

    def remaining(self, limit=None):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("Aggregate execution budget exhausted")
        return remaining if limit is None else min(limit, remaining)


@contextmanager
def budget(seconds):
    inherited = _budget.get()
    token = _budget.set(inherited or Budget(seconds))
    try:
        yield _budget.get()
    finally:
        _budget.reset(token)


def remaining(limit):
    current = _budget.get()
    return current.remaining(limit) if current else limit


def begin(kind, label, seconds, *, id=None):
    id = id or uuid.uuid4().hex
    with _lock:
        _active[id] = {"id": id, "kind": kind, "label": label[:140],
                       "started_at": time.time(), "deadline": time.monotonic() + remaining(seconds),
                       "last_progress": time.time()}
    return id


def finish(id):
    with _lock:
        _active.pop(id, None)


def snapshot():
    with _lock:
        return [{**entry, "remaining": max(0, entry["deadline"] - time.monotonic())}
                for entry in _active.values()]


def expired():
    return [entry for entry in snapshot() if not entry["remaining"]]
