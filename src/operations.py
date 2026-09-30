"""Monotonic budgets and observable operations shared by retries and tools."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
import uuid
import os
import signal
import subprocess

import turn_control


_budget: ContextVar = ContextVar("operation_budget", default=None)
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


def observe(event):
    """Only observable state, never commands, output or reasoning."""
    kind = event.get("type")
    part = event.get("part") or {}
    id = part.get("id")
    if kind == "tool_start" and id:
        tool = part.get("tool", "tool")
        if any(entry["id"] == id for entry in snapshot()):
            return
        limit = 600 if tool == "task" else 900 if tool == "bash" else 45
        begin("subagent" if tool == "task" else "tool", tool, limit, id=id)
    elif kind == "tool_use" and id:
        finish(id)
    elif kind == "session_status":
        sid = "provider:" + str(event.get("sourceSessionID") or event.get("sessionID"))
        status = event.get("status", {}).get("type")
        if status == "retry":
            if not any(entry["id"] == sid for entry in snapshot()):
                begin("provider", "provider retry", 180, id=sid)
        else:
            finish(sid)


def clear():
    with _lock:
        _active.clear()


def terminate(process, grace=3):
    """Signal the whole group even if its leader already exited."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def run(argv, *, cwd=None, env=None, timeout=900, input=None, kind="check", cleanup=None):
    operation = begin(kind, str(argv[0]), timeout)
    process = None
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        turn_control.register(process)
        try:
            stdout, stderr = process.communicate(input=input, timeout=remaining(timeout))
        except BaseException:
            terminate(process)
            raise
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    finally:
        kicked = turn_control.release(process) if process is not None else False
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
        try:
            if cleanup:
                cleanup()
        finally:
            finish(operation)
        if kicked:
            raise turn_control.TurnKicked("user requested KICK")
