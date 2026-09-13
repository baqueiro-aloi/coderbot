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
