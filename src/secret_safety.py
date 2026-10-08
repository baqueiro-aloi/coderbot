"""Shared redaction, including secrets acquired after process startup."""
import os
import re
import threading
import logging
import traceback


_lock = threading.RLock()
_values = set()
_NAME = re.compile(r'TOKEN|PASSWORD|SECRET|API_KEY|CREDENTIAL|PRIVATE_KEY', re.I)


def register(*values):
    with _lock:
        _values.update(value for value in values if isinstance(value, str) and len(value) >= 4)


def clear():
    """Clear an isolated registry; callers must not clear secrets mid-task."""
    with _lock:
        _values.clear()


def redact(text, environ=None):
    text = str(text)
    env = os.environ if environ is None else environ
    with _lock:
        values = _values | {value for name, value in env.items()
                             if _NAME.search(name) and isinstance(value, str) and len(value) >= 4}
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, '[REDACTED]')
    text = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)(bearer\s+)\S+', r'\1[REDACTED]', text)
    text = re.sub(r'''(?i)((?:[\w-]*(?:token|secret|password|api[_-]?key)[\w-]*)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s"']+)''',
                  r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:xox[baprs]-[\w-]+|sk-[\w-]+|gh[pousr]_[\w]+)\b', '[REDACTED]', text)
    text = re.sub(r'(?i)([?&](?:token|api_key|password|secret)=)[^&\s]+', r'\1[REDACTED]', text)
    return re.sub(r'(https?://)[^/\s:@]+:[^@\s/]+@', r'\1[REDACTED]@', text)


def safe(value, environ=None):
    if isinstance(value, str):
        return redact(value, environ)
    if isinstance(value, dict):
        return {key: safe(item, environ) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item, environ) for item in value]
    return value


class SecretFilter(logging.Filter):
    def filter(self, record):
        record.msg, record.args = redact(record.getMessage()), ()
        if record.exc_info:
            record.exc_text = redact(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def install_log_filters():
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, SecretFilter) for item in handler.filters):
            handler.addFilter(SecretFilter())
