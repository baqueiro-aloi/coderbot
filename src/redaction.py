"""One value-based secret redactor shared by logs, progress tails, diagnostics and reports.

Redaction is by *value* (credentials registered at startup or acquired later) plus a few
conservative token shapes. It deliberately has no ``key=value`` heuristics and no scan of
environment variable *names*: those mangled prompts and code in the past (e.g. every
"80000" vanished because ``CODEBOT_CONTEXT_TOKEN_BUDGET=80000`` matched ``TOKEN``).

Every public function is total: a redaction failure must never become a bot failure.
"""
import logging
import re
import threading

PLACEHOLDER = "[REDACTED]"
MIN_LENGTH = 8  # shorter values are too likely to collide with ordinary text

_lock = threading.Lock()
_values: set[str] = set()
_formatter = logging.Formatter()

# (pattern, keep-group-1). Shapes only; no generic assignment matching.
_PATTERNS = (
    (re.compile(r"\b(?:xox[abeprs]-[\w-]{6,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})"), False),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), False),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), False),
    (re.compile(r"(?i)(\b(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]{8,}"), True),
    (re.compile(r"(?i)([?&](?:token|api_key|apikey|password|secret|access_token|client_secret)=)[^&\s\"']+"), True),
    (re.compile(r"(https?://)[^/\s:@]+:[^@\s/]+(@)"), "userinfo"),
)


def register(*values) -> None:
    """Remember secret values to strip from every redacted text. Ignores non-strings/short values."""
    with _lock:
        for value in values:
            if isinstance(value, str):
                value = value.strip()
                if len(value) >= MIN_LENGTH:
                    _values.add(value)


def registered() -> list[str]:
    with _lock:
        return sorted(_values, key=len, reverse=True)


def clear() -> None:
    """Test hook."""
    with _lock:
        _values.clear()


def redact(text) -> str:
    try:
        text = text if isinstance(text, str) else str(text)
        for value in registered():
            text = text.replace(value, PLACEHOLDER)
        for pattern, keep in _PATTERNS:
            if keep == "userinfo":
                text = pattern.sub(r"\1" + PLACEHOLDER + r"\2", text)
            else:
                text = pattern.sub((r"\1" + PLACEHOLDER) if keep else PLACEHOLDER, text)
        return text
    except Exception:  # never let redaction itself fail a caller
        return text if isinstance(text, str) else PLACEHOLDER


class Filter(logging.Filter):
    """Rewrites each record's message in place. Never raises, never drops a record."""

    def filter(self, record):
        try:
            message = record.getMessage()
            record.msg = redact(message)
            record.args = ()
            if record.exc_info and not record.exc_text:
                record.exc_text = redact(_formatter.formatException(record.exc_info))
        except Exception:
            pass
        return True


def install() -> None:
    """Attach the filter to every root handler (a filter on the root *logger* does not see
    records propagated from child loggers)."""
    try:
        for handler in logging.getLogger().handlers:
            if not any(isinstance(f, Filter) for f in handler.filters):
                handler.addFilter(Filter())
    except Exception:
        pass
