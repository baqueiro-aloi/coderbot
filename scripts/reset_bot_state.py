"""Start a fresh task queue without discarding this installation's credentials or identity."""
import fcntl
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path


# Never touch instance_id, instance_fingerprint, token.json, credentials.json,
# opencode/, or processed_msgs.json (email redelivery deduplication).
TASK_FILES = (
    "state.json", "state.tmp", "holds.json", "holds.tmp",
    "slack_inbox.sqlite", "slack_inbox.sqlite-wal", "slack_inbox.sqlite-shm",
    "slack_inbox.sqlite-journal", "heartbeat",
)


def reset(data_dir: Path) -> Path | None:
    """Archive only task/conversation state; refuse while the bot holds its lock."""
    if not data_dir.is_dir():
        return None
    lock_path = data_dir / "state.lock"
    if lock_path.exists():
        with lock_path.open("rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Bot is running; stop it with docker compose stop codebot first") from error
            try:
                return _archive(data_dir)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    return _archive(data_dir)


def _archive(data_dir: Path) -> Path | None:
    files = [data_dir / name for name in TASK_FILES if (data_dir / name).exists()]
    if not files:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = data_dir / f"previous-task-state-{stamp}-{secrets.token_hex(4)}"
    backup.mkdir(mode=0o700)
    backup.chmod(0o700)
    for path in files:
        os.replace(path, backup / path.name)
    return backup


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent.parent / "data"
    try:
        archived = reset(directory)
    except (OSError, RuntimeError) as error:
        raise SystemExit(f"Could not reset task state: {error}") from error
    print(f"Task state archived in {archived}; bot will start IDLE."
          if archived else "No previous task state found; bot is already blank.")
