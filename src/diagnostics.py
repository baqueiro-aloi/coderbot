"""Complete redacted incident artifacts, independent of successful evidence runs."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import traceback


def redact(text, environ=None):
    text = str(text)
    env = os.environ if environ is None else environ
    secrets = {value for key, value in env.items()
               if re.search(r"TOKEN|PASSWORD|SECRET|API_KEY|CREDENTIAL", key, re.I)
               and len(value) >= 4}
    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:xox[baprs]-[\w-]+|gh[pousr]_[\w]+)\b", "[REDACTED]", text)
    text = re.sub(r"(?i)([?&](?:token|api_key|password|secret)=)[^&\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(https?://)[^/\s:@]+:[^@\s/]+@", r"\1[REDACTED]@", text)
    return text


def report(store, state, repo, directory, phase, *, error=None, detail="", identity=None):
    trace = "".join(traceback.format_exception(error)) if error is not None else ""
    fields = {"task": state.get("item"), "phase": phase,
              "attempt": state.get("execution_attempt_id"), "detail": detail,
              "traceback": trace}
    if error is not None:
        for key in ("cmd", "returncode", "stdout", "stderr", "output"):
            value = getattr(error, key, None)
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            if value is not None:
                fields[key] = value
    # Human-readable .txt: don't wrap conversation/logs in escaped JSON strings.
    text = redact(f"Task: {state.get('item', '-')}\nPhase: {phase}\n"
                  f"Attempt: {state.get('execution_attempt_id') or '-'}\n\n{detail}")
    for key in ("cmd", "returncode", "stdout", "stderr", "output"):
        if key in fields:
            text += "\n\n" + key + ":\n" + redact(fields[key])
    if trace:
        text += "\n\nFull exception chain:\n" + redact(trace)
    key = identity or hashlib.sha256(text.encode()).hexdigest()
    row = store.record("incident", state, repo, key, {"phase": phase}, status="recorded")
    folder = Path(directory) / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", phase.lower())
    path = folder / f"diagnostic-{name}-{row['id'][:12]}.txt"
    if not path.is_file():
        timestamp = datetime.fromtimestamp(row["created"], timezone.utc).isoformat()
        path.write_text(f"Incident: {row['id']}\nTime: {timestamp}\n{text}\n", encoding="utf-8")
    store.update("incident", row, path=str(path), hash=hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def summary(error=None, detail=""):
    value = str(error) if error else detail
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return "Outcome unavailable; diagnostic report recorded."
    final = next((line for line in lines if not line.startswith(("Task:", "State:", "PR:"))), lines[-1])
    if "Traceback" in value:
        final = lines[-1]
    if len(final) > 240 or final.startswith(("{", "[")):
        return "Execution failed; full details are in the diagnostic report."
    return redact(final)
