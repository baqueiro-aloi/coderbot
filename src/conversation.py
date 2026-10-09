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


def update_progress(thread_id: str | None, snapshot: dict) -> None:
    """Optional live progress; non-editable channels never send fallback messages."""
    update = getattr(_backend(), "update_progress", None)
    if thread_id and update is not None:
        update(thread_id, snapshot)


def flush_progress() -> None:
    """Retry optional queued progress, including final updates to retired tasks."""
    flush = getattr(_backend(), "flush_progress", None)
    if flush is not None:
        flush()


def deliver(state, subject, body, thread_id=None, attachments=()):
    import message_delivery
    import phase_checkpoint
    return message_delivery.deliver(phase_checkpoint.store(), state, config.REPO_PATH,
        config.DATA_DIR, _backend(), subject, body, thread_id, attachments)


def retry_deliveries(state):
    import message_delivery
    import phase_checkpoint
    store = phase_checkpoint.store()
    message_delivery.retry_pending(store, state, config.REPO_PATH, _backend())
    rows = store.list("delivery_receipt", store.task_identity(state, config.REPO_PATH), status="pending")
    if state.get("proposal_delivery_pending") and not rows:
        state.pop("proposal_delivery_pending", None)
        if state.get("replan"):
            row = store.get("feedback", state["replan"]["feedback_id"])
            if row:
                store.update("feedback", row, status="complete", outcome="revised proposal delivered")


def poll_command():
    return _backend().poll_command()


def poll_status(thread_id: str | None = None) -> tuple[str, str] | None:
    return _backend().poll_status(thread_id)


def poll_kick(thread_id: str | None = None) -> tuple[str, str] | None:
    return _backend().poll_kick(thread_id)


def poll_verify(thread_id: str | None = None):
    return _backend().poll_verify(thread_id)


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
