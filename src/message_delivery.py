"""Durable notification/file delivery independent from coding phase retries."""
import hashlib
import json
from pathlib import Path

import attachments


def deliver(store, state, repo, directory, backend, subject, body, thread_id, files=(), *, identity=None):
    for file in files:
        body = body.replace(Path(file).name, attachments.delivery_name(file))
    descriptors = [attachments.describe(file, role="diagnostic" if Path(file).suffix == ".txt"
                                        else "supporting") for file in files]
    identity = identity or hashlib.sha256(json.dumps([backend.__name__, subject, body, thread_id,
        [a["id"] for a in descriptors]], ensure_ascii=False).encode()).hexdigest()
    limits = backend.attachment_limits()
    prepared = [part for artifact in descriptors for part in attachments.prepare(
        artifact, limits["file"], Path(directory) / "transport", mime=limits["mime"])]
    row = store.record("delivery_receipt", state, repo, identity, {
        "envelope": {"id": identity[:32], "subject": subject, "body": body,
                     "thread_id": thread_id, "attachments": prepared}, "receipts": {},
        "channel": backend.__name__})
    return attempt(store, row, backend)


def attempt(store, row, backend):
    envelope = row["data"]["envelope"]
    receipts = dict(row["data"]["receipts"])
    for artifact in envelope["attachments"]:
        if receipts.get(artifact["id"], {}).get("status") == "confirmed":
            continue
        if attachments.describe(artifact["path"])["id"] != artifact["id"]:
            raise ValueError("Attachment content changed after delivery was queued")
    # A process can die after the provider accepted a file. Do not blindly resend
    # uncertain artifacts; adapters reconcile or expose uncertainty for inspection.
    for key, receipt in list(receipts.items()):
        if receipt.get("status") == "uncertain":
            try:
                reconciled = backend.reconcile_delivery(envelope, key, receipt)
            except Exception:
                reconciled = None
            if reconciled:
                receipts[key] = reconciled
    def confirm(key, value):
        receipts[key] = value
        store.update("delivery_receipt", row, status="pending", receipts=dict(receipts))
    error = None
    try:
        thread = backend.send_envelope(envelope, receipts, confirm)
    except Exception as exc:
        # Keep provider receipts and retry transport, never the coding phase.
        thread = row["data"].get("thread_id") or envelope.get("thread_id")
        error = f"{type(exc).__name__}: {exc}"
    required = ["body", *[a["id"] for a in envelope["attachments"]]]
    complete = all(receipts.get(key, {}).get("status") == "confirmed" for key in required)
    store.update("delivery_receipt", row, status="complete" if complete else "pending",
                  receipts=receipts, thread_id=thread, last_error=error)
    return {"thread_id": thread, "complete": complete, "receipts": receipts, "notification_id": row["id"], "error": error}


def retry_pending(store, state, repo, backend):
    task = store.task_identity(state, repo)
    for row in reversed(store.list("delivery_receipt", task, status="pending")):
        if row["data"].get("channel", backend.__name__) != backend.__name__:
            continue
        attempt(store, row, backend)
