"""Spawn and resume headless Claude Code sessions."""
import json
import logging
import os
import subprocess
from pathlib import Path

import config

log = logging.getLogger(__name__)

# claude keeps its mutable config here; HOME is /home/bot in the container.
CONFIG_PATH = Path(os.environ.get("CLAUDE_CONFIG_PATH") or (Path.home() / ".claude.json"))

SENTINEL = "NEED_USER_INPUT:"

# Claude runs with cwd = the target repo, which no longer contains codebot, so
# the outbox must be referenced by absolute path.
OUTBOX_DIR = (config.DATA_DIR / "outbox").resolve()

SENTINEL_CONTRACT = f"""
You are running headlessly with no interactive user. If at any point you need
the user to answer a question or make a decision, do NOT ask interactively.
Instead, END your response with a line starting exactly with `{SENTINEL}`
followed by the full question and all context needed to answer it by email,
then stop working. Otherwise finish the work and summarize what you did.
If a question is about visible UI behavior and a screenshot or short video would
help, save the file(s) under {OUTBOX_DIR}/ and list each one's ABSOLUTE path on
its own line starting with `ATTACH: ` before the {SENTINEL} line.
"""


class ClaudeResult:
    def __init__(self, session_id: str, output: str):
        self.session_id = session_id
        self.output = output

    @property
    def question(self) -> str | None:
        idx = self.output.rfind(SENTINEL)
        return self.output[idx + len(SENTINEL):].strip() if idx >= 0 else None

    @property
    def attachments(self) -> list[str]:
        # Model output is influenced by untrusted email content, so confine
        # attachment paths to the outbox dir to prevent host-file exfiltration.
        valid = []
        for line in self.output.splitlines():
            if not line.startswith("ATTACH:"):
                continue
            # Joining with an absolute path yields that path; the join only
            # kicks in for (out-of-contract) repo-relative ones.
            candidate = (config.REPO_PATH / line[len("ATTACH:"):].strip()).resolve()
            if candidate.is_relative_to(OUTBOX_DIR) and candidate.is_file():
                valid.append(str(candidate))
        return valid


def _config_report() -> str:
    """One-line health summary of ~/.claude.json, for diagnosing corruption."""
    try:
        raw = CONFIG_PATH.read_bytes()
    except OSError as err:
        return f"{CONFIG_PATH}: unreadable ({err})"
    try:
        json.loads(raw)
        parses = "OK"
    except ValueError as err:
        parses = f"FAIL ({err})"
    mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0
    return f"{CONFIG_PATH}: {len(raw)} bytes, mtime={mtime:.0f}, parses={parses}"


def _is_config_corrupt(stderr: str) -> bool:
    return "configuration file" in stderr and "corrupted" in stderr


def _restore_config() -> bool:
    """Repair a corrupt ~/.claude.json: restore the newest parseable backup claude wrote,
    else reset to an empty object. Returns True if a valid config is now in place."""
    backups = sorted((Path.home() / ".claude" / "backups").glob(".claude.json.backup.*"))
    for backup in reversed(backups):
        try:
            data = backup.read_bytes()
            json.loads(data)
        except (OSError, ValueError):
            continue
        CONFIG_PATH.write_bytes(data)
        log.warning("restored %s from backup %s", CONFIG_PATH, backup.name)
        return True
    try:
        CONFIG_PATH.write_text("{}")
        log.warning("no parseable backup; reset %s to empty object", CONFIG_PATH)
        return True
    except OSError as err:
        log.error("could not reset %s: %s", CONFIG_PATH, err)
        return False


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=config.REPO_PATH, capture_output=True, text=True,
                          timeout=config.CLAUDE_TIMEOUT_SECONDS)


def _invoke(args: list[str], prompt: str) -> ClaudeResult:
    cmd = ["claude", *args, "-p", prompt, "--model", config.CLAUDE_MODEL,
           "--dangerously-skip-permissions", "--output-format", "json"]
    log.info("claude %s model=%s (prompt %d chars); config %s",
             " ".join(args) or "run", config.CLAUDE_MODEL, len(prompt), _config_report())
    proc = _run(cmd)
    if proc.returncode != 0 and _is_config_corrupt(proc.stderr):
        # ~/.claude.json got corrupted (historically by a concurrent writer sharing the
        # file). Snapshot its state, repair it, and retry once before giving up.
        log.error("claude reported a corrupt config; %s", _config_report())
        if _restore_config():
            log.info("retrying claude after config recovery")
            proc = _run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[-2000:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"claude returned non-JSON output: {proc.stdout[:2000]!r}") from err
    if "session_id" not in data:
        raise RuntimeError(f"claude output missing session_id: {proc.stdout[:2000]!r}")
    result = ClaudeResult(session_id=data["session_id"], output=data.get("result", ""))
    log.info("claude returned session=%s output=%d chars sentinel=%s",
             result.session_id, len(result.output), result.question is not None)
    log.debug("claude output:\n%s", result.output)
    return result


def run(prompt: str) -> ClaudeResult:
    return _invoke([], SENTINEL_CONTRACT + "\n\n" + prompt)


def resume(session_id: str, prompt: str) -> ClaudeResult:
    return _invoke(["--resume", session_id], prompt)
