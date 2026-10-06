"""Transport-neutral parsing of existing Codebot text commands."""
import re

COMMANDS = ("ABORT", "STATUS", "KICK", "DONE", "HOLD", "PAUSE", "CONTINUE", "RESUME", "VERIFY")
_ALIASES = {"PAUSE": "HOLD", "RESUME": "CONTINUE"}
_CMD_RE = re.compile(r"^(ABORT|STATUS|KICK|DONE|HOLD|PAUSE)(?:\s+([\w.-]*[\w-]))?\s*[?!.]*\s*$",
                     re.IGNORECASE)
_CONTINUE_RE = re.compile(
    r"^(CONTINUE|RESUME)\b(?:\s+(codebot[\w.-]*[\w-]))?\s*[:,.!-]*\s*(.*)$",
    re.IGNORECASE | re.DOTALL)
_VERIFY_RE = re.compile(r"^VERIFY\b(?:\s+(codebot[\w.-]*[\w-]))?\s*[:,.!]*\s*(.*)$",
                        re.IGNORECASE | re.DOTALL)


def parse_command(body: str) -> tuple[str, str, str] | None:
    text = body.strip()
    match = _VERIFY_RE.match(text)
    if match:
        return "VERIFY", (match.group(1) or "").lower(), match.group(2).strip()
    match = _CMD_RE.match(text)
    if match:
        return _ALIASES.get(match.group(1).upper(), match.group(1).upper()), (match.group(2) or "").lower(), ""
    match = _CONTINUE_RE.match(text)
    if match:
        return "CONTINUE", (match.group(2) or "").lower(), match.group(3).strip()
    return None


def foreign_command(body: str, instance: str) -> str | None:
    parsed = parse_command(body)
    if parsed:
        target = parsed[1]
        return target if target and target != instance else None
    return None
