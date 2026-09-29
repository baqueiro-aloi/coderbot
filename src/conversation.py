"""User conversation façade: email threads or per-task Slack threads."""
from pathlib import Path

import config


def _backend():
    if config.COMM_CHANNEL == "email":
        import gmail_client
        return gmail_client
    if config.COMM_CHANNEL == "slack":
        import slack_client
        return slack_client
    raise RuntimeError(f"unsupported CODEBOT_COMM_CHANNEL: {config.COMM_CHANNEL!r}")


def open_thread(state: dict) -> str | None:
    if config.COMM_CHANNEL == "email":
        return None  # Gmail opens the thread on the first outgoing message.
    return _backend().open_thread(state)


def send(subject: str, body: str, thread_id: str | None = None,
         attachments: list[Path] | None = None, *, progress: Path | None = None) -> str:
    if progress is not None:
        return _backend().send(subject, body, thread_id, attachments, progress=progress)
    return _backend().send(subject, body, thread_id, attachments)


def poll_command():
    return _backend().poll_command()


def poll_reply(thread_id: str):
    return _backend().poll_reply(thread_id)


def mark_processed(message_id: str) -> None:
    _backend().mark_processed(message_id)


def drain_thread(thread_id: str) -> int:
    return _backend().drain_thread(thread_id)


def foreign_command(body: str) -> str | None:
    from command_text import foreign_command as parse_foreign
    return parse_foreign(body, config.INSTANCE_ID)


def start() -> None:
    if config.COMM_CHANNEL == "slack":
        _backend().start()


def announce(body: str) -> None:
    """One-way operational notice; it never becomes an owned task thread."""
    if config.COMM_CHANNEL == "slack":
        _backend().announce(body)


def close_thread(thread_id: str | None) -> None:
    if config.COMM_CHANNEL == "slack":
        _backend().close_thread(thread_id)


def wait(seconds: float) -> None:
    if config.COMM_CHANNEL == "slack":
        _backend().wait(seconds)
    else:
        import time
        time.sleep(seconds)
