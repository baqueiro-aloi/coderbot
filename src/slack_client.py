"""One Slack app per installation: Socket Mode inbox and per-task threads.

The socket callback only commits incoming messages; the existing FSM executes
them between agent turns. SQLite is also the persistent owned-thread registry.
"""
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import config
from command_text import parse_command

log = logging.getLogger(__name__)
_socket = None
_web = None
_bot_user = None
_wake = threading.Event()


@contextmanager
def _database():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DATA_DIR / "slack_inbox.sqlite", timeout=15)
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("CREATE TABLE IF NOT EXISTS roots (channel TEXT NOT NULL, root_ts TEXT NOT NULL, "
               "nonce TEXT UNIQUE NOT NULL, PRIMARY KEY(channel, root_ts))")
    db.execute("CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, channel TEXT NOT NULL, "
               "root_ts TEXT NOT NULL, ts TEXT NOT NULL, text TEXT NOT NULL, handled INTEGER NOT NULL DEFAULT 0)")
    try:
        db.commit()
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _thread_id(channel: str, root_ts: str) -> str:
    return f"{channel}:{root_ts}"


def _split_thread(thread_id: str) -> tuple[str, str]:
    channel, root_ts = thread_id.split(":", 1)
    return channel, root_ts


def web():
    global _web
    if _web is None:
        from slack_sdk import WebClient
        _web = WebClient(token=config.SLACK_BOT_TOKEN, timeout=30)
    return _web


def validate() -> None:
    """Reject missing channel access before the first task is claimed."""
    global _bot_user
    info = web().auth_test()
    _bot_user = info["user_id"]
    headers = getattr(info, "headers", {}) or {}
    granted = {scope.strip() for scope in headers.get("x-oauth-scopes", "").split(",") if scope.strip()}
    required = {"chat:write", "channels:read", "channels:history", "files:write"}
    if granted and (missing := required - granted):
        raise RuntimeError(f"Slack bot token is missing scopes: {', '.join(sorted(missing))}")
    channel = web().conversations_info(channel=config.SLACK_CHANNEL_ID)["channel"]
    if channel.get("is_private") or not channel.get("is_channel"):
        raise RuntimeError("CODEBOT_SLACK_CHANNEL_ID must identify a public Slack channel")
    if not channel.get("is_member"):
        raise RuntimeError("Invite this instance's Slack app to the configured public channel")


def _accept_event(payload: dict) -> bool:
    event = payload.get("event") or {}
    if (event.get("type") != "message" or event.get("subtype") or event.get("bot_id")
            or not event.get("user") or event.get("user") == _bot_user
            or event.get("channel") != config.SLACK_CHANNEL_ID):
        return False
    root = event.get("thread_ts")
    if not root or root == event.get("ts") or not event.get("ts"):
        return False  # root/top-level messages are never commands
    channel = event["channel"]
    with _database() as db:
        if not db.execute("SELECT 1 FROM roots WHERE channel=? AND root_ts=?",
                          (channel, root)).fetchone():
            return False
        db.execute("INSERT OR IGNORE INTO messages(id,channel,root_ts,ts,text) VALUES(?,?,?,?,?)",
                   (_thread_id(channel, event["ts"]), channel, root, event["ts"],
                    event.get("text") or ""))
    _wake.set()
    return True


def _socket_request(client, request) -> None:
    from slack_sdk.socket_mode.response import SocketModeResponse
    try:
        if request.type == "events_api":
            _accept_event(request.payload)
    except Exception:
        # Do not acknowledge an event that could not be committed: Slack retries it.
        log.exception("failed to persist Slack event before acknowledgment")
        return
    client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))


def start() -> None:
    global _socket
    if _socket is not None:
        return
    validate()
    from slack_sdk.socket_mode import SocketModeClient
    client = SocketModeClient(app_token=config.SLACK_APP_TOKEN, web_client=web(),
                              auto_reconnect_enabled=True)
    client.socket_mode_request_listeners.append(_socket_request)
    client.connect()
    _socket = client


def wait(seconds: float) -> None:
    _wake.wait(seconds)
    _wake.clear()


def announce(body: str) -> None:
    web().chat_postMessage(channel=config.SLACK_CHANNEL_ID, text=body,
                           unfurl_links=False)


def open_thread(state: dict) -> str:
    """Recover by nonce after an uncertain send; never create a second root."""
    nonce = state.get("thread_nonce") or state.get("branch")
    if not nonce:
        raise RuntimeError("cannot start a Slack task thread without a persisted task nonce")
    channel = config.SLACK_CHANNEL_ID
    with _database() as db:
        found = db.execute("SELECT root_ts FROM roots WHERE nonce=?", (nonce,)).fetchone()
    if found:
        return _thread_id(channel, found[0])
    marker = f"[codebot-task:{nonce}]"
    # A crash may have occurred after Slack accepted the post but before its ID
    # reached state.json or SQLite. Search our own roots before posting again.
    cursor = None
    for _page in range(5):
        args = {"channel": channel, "limit": 100}
        if cursor:
            args["cursor"] = cursor
        page = web().conversations_history(**args)
        match = next((msg for msg in page.get("messages", [])
                      if msg.get("user") == _bot_user and marker in msg.get("text", "")), None)
        if match:
            root_ts = match["ts"]
            break
        cursor = (page.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            root_ts = None
            break
    else:
        # A truncated history is ambiguous; never risk a duplicate root.
        raise RuntimeError(f"cannot reconcile Slack task root {marker} in channel history")
    if not root_ts:
        title = state.get("item", "(unnamed task)")
        link = state.get("item_url")
        text = f"*{config.INSTANCE_ID}* picked: {title}" + (f"\nSource: {link}" if link else "")
        root_ts = web().chat_postMessage(channel=channel, text=f"{text}\n{marker}",
                                          unfurl_links=False)["ts"]
    with _database() as db:
        db.execute("INSERT OR IGNORE INTO roots(channel,root_ts,nonce) VALUES(?,?,?)",
                   (channel, root_ts, nonce))
    return _thread_id(channel, root_ts)


def close_thread(thread_id: str | None) -> None:
    if not thread_id:
        return
    channel, root_ts = _split_thread(thread_id)
    with _database() as db:
        db.execute("DELETE FROM roots WHERE channel=? AND root_ts=?", (channel, root_ts))


def _chunks(body: str, limit: int = 3800):
    while len(body) > limit:
        index = body.rfind("\n", 0, limit)
        if index < limit // 2:
            index = limit
        else:
            index += 1  # keep the boundary newline in the outgoing text
        yield body[:index]
        body = body[index:]
    if body:
        yield body


def send(subject: str, body: str, thread_id: str | None = None,
         attachments: list[Path] | None = None) -> str:
    if not thread_id:
        raise RuntimeError("Slack task messages require an owned task thread")
    channel, root_ts = _split_thread(thread_id)
    for part in _chunks(body):
        web().chat_postMessage(channel=channel, thread_ts=root_ts, text=part,
                               unfurl_links=False)
    for path in attachments or []:
        try:
            web().files_upload_v2(channel=channel, thread_ts=root_ts,
                                  file=str(path), filename=path.name)
        except Exception:
            log.exception("could not share %s in Slack thread", path.name)
            web().chat_postMessage(channel=channel, thread_ts=root_ts,
                                   text=f"Evidence file unavailable: {path.name}")
    return thread_id


def _pending(thread_id: str | None = None):
    clause, args = "", []
    if thread_id:
        channel, root_ts = _split_thread(thread_id)
        clause = " AND m.channel=? AND m.root_ts=?"
        args = [channel, root_ts]
    with _database() as db:
        return db.execute(
            "SELECT m.id,m.text,m.channel,m.root_ts FROM messages m "
            "JOIN roots r ON r.channel=m.channel AND r.root_ts=m.root_ts "
            "WHERE m.handled=0" + clause + " ORDER BY CAST(m.ts AS REAL),m.ts", args).fetchall()


def poll_command():
    for msg_id, text, channel, root_ts in _pending():
        parsed = parse_command(text)
        if not parsed:
            continue
        command, target, note = parsed
        if target and target != config.INSTANCE_ID:
            mark_processed(msg_id)
            continue
        return msg_id, _thread_id(channel, root_ts), command, bool(target), note
    return None


def poll_reply(thread_id: str):
    for msg_id, text, _channel, _root in _pending(thread_id):
        if text.strip():
            return msg_id, text.strip()
        mark_processed(msg_id)
    return None


def mark_processed(message_id: str) -> None:
    with _database() as db:
        db.execute("UPDATE messages SET handled=1 WHERE id=?", (message_id,))


def drain_thread(thread_id: str) -> int:
    pending = _pending(thread_id)
    for msg_id, _text, _channel, _root in pending:
        mark_processed(msg_id)
    return len(pending)
