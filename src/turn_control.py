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
_processes = {}
_kicked = set()


def register(process: subprocess.Popen) -> None:
    global _process, _requested
    with _lock:
        _process = process
        _requested = False
        _processes[process.pid] = process


def release(process: subprocess.Popen) -> bool:
    global _process, _requested
    with _lock:
        _processes.pop(process.pid, None)
        was_kicked = process.pid in _kicked
        _kicked.discard(process.pid)
        if _process is not process:
            return was_kicked
        kicked = _requested or was_kicked
        _process = None
        _requested = False
        return kicked


def request_kick() -> bool:
    """SIGTERM the agent's own process group; escalate after a short grace period."""
    global _requested
    with _lock:
        processes = [p for p in _processes.values() if p.poll() is None]
        if not processes:
            return False
        if _requested:
            return True
        _requested = True
        for proc in processes:
            _kicked.add(proc.pid)
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def escalate() -> None:
        with _lock:
            for proc in processes:
                if proc.pid in _processes and proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    timer = threading.Timer(3, escalate)
    timer.daemon = True
    timer.start()
    return True
