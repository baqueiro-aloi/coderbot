"""Backend-neutral helpers for backlog item text.

Shared by every task source (Google Doc, GitHub Projects) and by main.py, so the
identity comparison and the Codebot[n] ordering tag mean the same thing everywhere.
"""
import re


def normalize(text: str) -> str:
    """Whitespace-collapsed, lower-cased text: the identity comparison for items."""
    return re.sub(r"\s+", " ", text).strip().lower()


# Optional ordering tag the user writes in a task's text ("Codebot[1]", "codebot[2]"):
# tagged tasks are picked before untagged ones, in ascending order.
PRIORITY_RE = re.compile(r"\bcodebot\s*\[\s*(\d+)\s*\]", re.IGNORECASE)


def priority_of(text: str) -> int | None:
    """The Codebot[n] ordering number in the text, or None when untagged."""
    m = PRIORITY_RE.search(text)
    return int(m.group(1)) if m else None


class MalformedPayload(RuntimeError):
    """A backend answered with a payload that lacks a required collection.

    Distinct from "empty backlog": an API that drops the `items`/`issues`/`content`
    list (schema change, partial outage, truncated body) must not be read as "there is
    nothing to do". main treats this as a transient error and retries with backoff.
    Lives here (not in task_source) so tests that stub the task_source module keep it.
    """


def require_list(payload, key: str, context: str) -> list:
    """`payload[key]` when it is a list; MalformedPayload otherwise (missing, null, wrong type)."""
    value = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(value, list):
        kind = "missing" if not isinstance(payload, dict) or key not in payload else type(value).__name__
        raise MalformedPayload(f"{context}: expected a list under {key!r}, got {kind}")
    return value
