"""Send/receive correlated email threads via the Gmail API."""
import base64
import json
import logging
import mimetypes
import re
from email.message import EmailMessage
from pathlib import Path

from googleapiclient.discovery import build

import config
from google_auth import load_credentials

try:
    import markdown as _markdown
except ImportError:  # keep sending (plain-text only) if the optional dep is missing
    _markdown = None

log = logging.getLogger(__name__)


def _markdown_to_html(text: str) -> str | None:
    """Render a Markdown body as a self-contained, Gmail-friendly HTML fragment.

    Gmail strips <head>/<style>, so we only emit basic inline-styled tags that it
    renders reliably. Returns None when the markdown lib is unavailable.
    """
    if _markdown is None:
        return None
    body = _markdown.markdown(
        text, extensions=["fenced_code", "tables", "sane_lists", "nl2br"])
    # Minimal inline styling for the few blocks Gmail won't style on its own.
    body = body.replace(
        "<pre>",
        '<pre style="background:#f6f8fa;padding:12px;border-radius:6px;'
        'overflow:auto;font-family:Menlo,Consolas,monospace;font-size:13px">')
    body = body.replace(
        "<code>",
        '<code style="background:#f6f8fa;padding:1px 4px;border-radius:4px;'
        'font-family:Menlo,Consolas,monospace;font-size:13px">')
    return ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
            f'line-height:1.5;color:#1a1a1a">{body}</div>')


def _gmail():
    return build("gmail", "v1", credentials=load_credentials(), cache_discovery=False)


def _strip_quoted(body: str) -> str:
    """Best-effort removal of quoted history from a reply body."""
    lines = []
    for line in body.splitlines():
        if re.match(r"^\s*On .{5,120} wrote:\s*$", line) or re.match(r"^\s*El .{5,120} escribi", line):
            break
        if line.startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    return ""


def send(subject: str, body: str, thread_id: str | None = None,
         attachments: list[Path] | None = None) -> str:
    """Send an email to the user; returns the Gmail thread id."""
    service = _gmail()
    msg = EmailMessage()
    msg["To"] = config.USER_EMAIL
    msg["From"] = config.USER_EMAIL
    # Same account sends and receives; this header lets poll_reply skip our own mail.
    msg["X-Codebot"] = "1"
    skipped = []

    if thread_id:
        # Reply within the existing thread: reuse its subject and last Message-Id.
        thread = service.users().threads().get(userId="me", id=thread_id, format="metadata").execute()
        headers = {h["name"].lower(): h["value"] for h in thread["messages"][-1]["payload"]["headers"]}
        msg["Subject"] = headers.get("subject", subject)
        if headers.get("message-id"):
            msg["In-Reply-To"] = headers["message-id"]
            prior = headers.get("references", "").strip()
            msg["References"] = f"{prior} {headers['message-id']}".strip()
    else:
        msg["Subject"] = subject

    total = 0
    files = []
    for path in attachments or []:
        size = path.stat().st_size
        if total + size > config.MAX_ATTACHMENT_BYTES:
            skipped.append(path)
            continue
        total += size
        files.append(path)
    if skipped:
        log.warning("omitting %d attachment(s) over %d-byte cap: %s",
                    len(skipped), config.MAX_ATTACHMENT_BYTES, [str(p) for p in skipped])
        body += "\n\nAttachments omitted (size limit): " + ", ".join(str(p) for p in skipped)
    msg.set_content(body)
    # Attach an HTML alternative so Gmail renders Markdown instead of showing raw
    # '#', '*', '`' etc. Must be added before any attachment (multipart ordering).
    html = _markdown_to_html(body)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in files:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        log.debug("attaching %s (%s, %d bytes)", path.name, ctype, path.stat().st_size)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    sent = service.users().messages().send(userId="me", body=payload).execute()
    log.info("sent message id=%s thread=%s (%d attachment(s), %d bytes total)",
             sent["id"], sent["threadId"], len(files), total)
    return sent["threadId"]


def _processed_path():
    return config.DATA_DIR / "processed_msgs.json"


def _load_processed() -> list[str]:
    path = _processed_path()
    return json.loads(path.read_text()) if path.exists() else []


def _save_processed(ids: list[str]) -> None:
    # Replies come from the same account, so UNREAD is never set on them;
    # we track consumed message ids ourselves instead. Insertion order, so
    # truncation drops the oldest entries.
    path = _processed_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ids[-500:]))
    tmp.replace(path)


def mark_processed(message_id: str) -> None:
    """Record a reply as consumed. Call this ONLY after the reply has been fully
    handled — marking it earlier drops the message for good if handling then crashes."""
    processed = _load_processed()
    if message_id not in processed:
        processed.append(message_id)
        _save_processed(processed)


def poll_abort() -> tuple[str, str] | None:
    """Scan recent mail for a user 'ABORT' command; returns (message_id, thread_id) or None.

    Mailbox-wide (any thread, or a brand-new email) rather than thread-scoped, so it works
    as a last resort even when the agent is stuck on a thread it no longer polls. Skips
    codebot's own mail (X-Codebot header) and already-processed messages, and matches only
    when the reply body is exactly 'ABORT' (case-insensitive) so it can't fire by accident.
    """
    service = _gmail()
    processed = _load_processed()
    listing = service.users().messages().list(
        userId="me", q="ABORT newer_than:2d", maxResults=25).execute()
    for meta in listing.get("messages", []):
        if meta["id"] in processed:
            continue
        message = service.users().messages().get(userId="me", id=meta["id"], format="full").execute()
        headers = {h["name"].lower() for h in message.get("payload", {}).get("headers", [])}
        if "x-codebot" in headers:
            continue
        body = _strip_quoted(_extract_body(message.get("payload", {})))
        if body.strip().upper() == "ABORT":
            log.warning("ABORT command received (msg %s, thread %s)",
                        meta["id"], message.get("threadId"))
            return meta["id"], message.get("threadId")
    return None


def poll_reply(thread_id: str) -> tuple[str, str] | None:
    """Return (message_id, body) of the newest unprocessed non-codebot reply, else None.

    Does NOT mark the message processed; the caller must call mark_processed() once it
    has successfully handled the reply. Marking here previously dropped the user's reply
    permanently whenever handling crashed afterwards (e.g. a transient claude failure).
    """
    service = _gmail()
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    processed = _load_processed()
    for message in reversed(thread.get("messages", [])):
        if message["id"] in processed:
            continue
        headers = {h["name"].lower() for h in message.get("payload", {}).get("headers", [])}
        if "x-codebot" in headers:
            continue
        body = _strip_quoted(_extract_body(message.get("payload", {})))
        if body:
            log.info("new reply in thread %s (msg %s, %d chars)", thread_id, message["id"], len(body))
            return message["id"], body
        # Empty after quote-strip: nothing to hand off, so consume it now to avoid rescan.
        mark_processed(message["id"])
        log.debug("reply msg %s had empty body after quote-strip; skipping", message["id"])
    return None
