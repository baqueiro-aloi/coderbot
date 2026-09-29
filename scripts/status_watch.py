"""Temporary out-of-process STATUS watcher for a bot already mid-agent-turn.

Can run inside its existing container without restarting PID 1. Never acquires the
state lock, touches the working checkout, or consumes anything except STATUS.
Exits when the original task/phase is no longer active. New container starts use
the built-in status supervisor instead.
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
import main as codebot  # noqa: E402
import slack_client  # noqa: E402


log = logging.getLogger("status-watch")


def watch(interval: float = 5) -> None:
    if config.COMM_CHANNEL != "slack":
        raise RuntimeError("the standalone watcher is for Slack deployments")
    initial = codebot.load_state()
    identity = (initial.get("thread_id"), initial.get("item"), initial.get("state"))
    if not all(identity) or identity[2] not in codebot.PHASES:
        raise RuntimeError("no active working task thread to supervise")
    thread = identity[0]
    log.info("watching task thread %s during %s", thread, identity[2])
    while True:
        state = codebot.load_state()
        if (state.get("thread_id"), state.get("item"), state.get("state")) != identity:
            log.info("task moved on; standalone watcher stopping")
            return
        try:
            request = slack_client.poll_status(thread)
            if request:
                message_id, reply_thread = request
                # No live agent memory is available in this independent process;
                # report only the persisted phase and be explicit about uncertainty.
                body = codebot._short_status(state, {"active": False}, time.time())
                slack_client.send(codebot.subject(state, "brief status"), body, reply_thread)
                slack_client.mark_processed(message_id)
                log.info("answered STATUS %s", message_id)
        except Exception:  # noqa: BLE001 — keep supervising after a transient Slack error
            log.exception("status check failed; retrying")
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(filename=config.DATA_DIR / "status-watch.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    watch()
