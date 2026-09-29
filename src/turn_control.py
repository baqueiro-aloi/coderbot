"""Interrupt only the current coding CLI process group, never codebot's FSM."""
import os
import signal
import subprocess
import threading


class TurnKicked(BaseException):
    """An explicit user-requested restart, not a phase failure or an abort."""


_lock = threading.Lock()
_process: subprocess.Popen | None = None
_requested = False


def register(process: subprocess.Popen) -> None:
    global _process, _requested
    with _lock:
        _process = process
        _requested = False


def release(process: subprocess.Popen) -> bool:
    global _process, _requested
    with _lock:
        if _process is not process:
            return False
        kicked = _requested
        _process = None
        _requested = False
        return kicked


def request_kick() -> bool:
    """SIGTERM the agent's own process group; escalate after a short grace period."""
    global _requested
    with _lock:
        proc = _process
        if proc is None or proc.poll() is not None:
            return False
        if _requested:
            return True
        _requested = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return True  # raced with exit; release still records the kick

    def escalate() -> None:
        with _lock:
            if _process is proc and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    timer = threading.Timer(3, escalate)
    timer.daemon = True
    timer.start()
    return True
