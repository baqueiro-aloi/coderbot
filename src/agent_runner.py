"""Run the configured headless coding agent and normalize its result."""
import json
import logging
import os
import subprocess
import threading

import claude_runner
import config

log = logging.getLogger(__name__)
# Live account of what the agent is doing (tool calls as they complete, text as it is
# emitted), so `docker compose logs -f` shows progress during a run instead of one
# "opencode resume" line followed by silence for an hour.
stream_log = logging.getLogger("agent")

STREAM_TEXT_MAX_CHARS = 1500
STREAM_DETAIL_MAX_CHARS = 300

SENTINEL = claude_runner.SENTINEL
OUTBOX_DIR = claude_runner.OUTBOX_DIR
EVIDENCE_CONTRACT = claude_runner.EVIDENCE_CONTRACT

_SESSION_RECOVERY_CONTEXT = """
The previous OpenCode session is unavailable. Continue this task autonomously from
the repository's current branch and working tree. Reconstruct any needed context
from the OpenSpec change artifacts and git history before acting; do not ask the
user to repeat information that is available there.
"""


def _opencode_environment() -> dict[str, str]:
    env = os.environ.copy()
    try:
        inline = json.loads(env.get("OPENCODE_CONFIG_CONTENT") or "{}")
    except json.JSONDecodeError as err:
        raise RuntimeError("OPENCODE_CONFIG_CONTENT must contain valid JSON") from err
    if not isinstance(inline, dict):
        raise RuntimeError("OPENCODE_CONFIG_CONTENT must contain a JSON object")

    plugins = inline.get("plugin", [])
    skills = inline.get("skills", {})
    if not isinstance(plugins, list) or not isinstance(skills, dict):
        raise RuntimeError("OPENCODE_CONFIG_CONTENT plugin/skills values have invalid types")
    paths = skills.get("paths", [])
    if not isinstance(paths, list):
        raise RuntimeError("OPENCODE_CONFIG_CONTENT skills.paths must be an array")
    if not all(isinstance(plugin, str) for plugin in plugins):
        raise RuntimeError("OPENCODE_CONFIG_CONTENT plugin entries must be strings")
    if not all(isinstance(path, str) for path in paths):
        raise RuntimeError("OPENCODE_CONFIG_CONTENT skills.paths entries must be strings")

    managed_plugins = [str(config.SUPERPOWERS_PLUGIN_DIR), str(config.BRIDGE_PLUGIN_DIR)]
    inline["plugin"] = list(dict.fromkeys([*plugins, *managed_plugins]))
    inline.update(model=config.OPENCODE_MODEL, share="disabled", autoupdate=False)
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(inline)
    return env


class OpenCodeResult:
    def __init__(self, session_id: str, output: str):
        self.session_id = session_id
        self.output = output

    @property
    def question(self) -> str | None:
        return claude_runner.sentinel_question(self.output)

    @property
    def preamble(self) -> str:
        return claude_runner.sentinel_preamble(self.output)

    @property
    def attachments(self) -> list[str]:
        # Delegate path validation to the established implementation.
        return claude_runner.ClaudeResult(self.session_id, self.output).attachments


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split()) if "\n" not in text.strip() else text.strip()
    return text if len(text) <= limit else text[:limit] + " [...]"


def summarize_event(event: dict) -> str | None:
    """One log line for an OpenCode JSON event, or None for events not worth a line.
    Shapes (from `opencode run --format json`): {"type":"text","part":{"text":..}},
    {"type":"tool_use","part":{"tool":..,"state":{"status","input","output","title"}}},
    {"type":"step_start"|"step_finish","part":{..}}, {"type":"error","error":..}."""
    kind = event.get("type")
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    if kind == "text":
        text = part.get("text")
        text = text.strip() if isinstance(text, str) else ""
        return f"[agent] {_clip(text, STREAM_TEXT_MAX_CHARS)}" if text else None
    if kind == "tool_use" or part.get("type") == "tool":
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        inputs = state.get("input") if isinstance(state.get("input"), dict) else {}
        detail = None
        for key in ("command", "filePath", "path", "pattern", "description", "prompt", "url"):
            if isinstance(inputs.get(key), str) and inputs[key].strip():
                detail = inputs[key]
                break
        if detail is None:
            detail = state.get("title") if isinstance(state.get("title"), str) else None
        if detail is None:
            detail = json.dumps(inputs, ensure_ascii=False) if inputs else ""
        line = f"[tool {part.get('tool', '?')}] {_clip(detail, STREAM_DETAIL_MAX_CHARS)}".rstrip()
        if state.get("status") == "error":
            line += f" -> ERROR: {_clip(str(state.get('error', '')), STREAM_DETAIL_MAX_CHARS)}"
        return line
    if kind == "error":
        return f"[error] {_clip(str(event.get('error', 'unknown OpenCode error')), STREAM_DETAIL_MAX_CHARS)}"
    if kind == "step_finish":
        tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        total = tokens.get("total")
        return f"[step] {part.get('reason', 'finished')}" + (f" tokens={total}" if total else "")
    return None


def _stream_line(line: str) -> None:
    try:
        event = json.loads(line)
    except ValueError:
        return  # the final parse in _opencode reports malformed events
    if not isinstance(event, dict):
        return
    summary = summarize_event(event)
    if summary is None:
        return
    stream_log.log(logging.DEBUG if summary.startswith("[step]") else logging.INFO, "%s", summary)


def _run_streaming(cmd: list[str], *, cwd, env: dict[str, str], timeout: float,
                   on_line=_stream_line) -> subprocess.CompletedProcess:
    """subprocess.run(capture_output=True, text=True, timeout=...) equivalent that hands
    every stdout line to on_line as it arrives. Raises subprocess.TimeoutExpired (with
    the partial output) after killing the process, as subprocess.run would."""
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    stderr_chunks: list[str] = []
    stderr_reader = threading.Thread(
        target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True)
    stderr_reader.start()
    timed_out = threading.Event()

    def _kill_on_timeout() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout, _kill_on_timeout)
    timer.daemon = True
    timer.start()
    stdout_lines: list[str] = []
    try:
        for line in proc.stdout:
            stdout_lines.append(line)
            try:
                on_line(line.rstrip("\n"))
            except Exception:  # noqa: BLE001 — logging must never abort the run
                log.exception("agent stream logging failed")
        proc.wait()
    finally:
        timer.cancel()
        stderr_reader.join(timeout=5)
        proc.stdout.close()
        proc.stderr.close()
    stdout, stderr = "".join(stdout_lines), "".join(stderr_chunks)
    if timed_out.is_set():
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _opencode(prompt: str, session_id: str | None = None) -> OpenCodeResult:
    cmd = ["opencode", "run", "--dir", str(config.REPO_PATH), "--model", config.OPENCODE_MODEL,
           "--auto", "--format", "json"]
    if session_id:
        cmd.extend(["--session", session_id])
    cmd.append(prompt)
    log.info("opencode %s model=%s (prompt %d chars)",
             "resume" if session_id else "run", config.OPENCODE_MODEL, len(prompt))
    proc = _run_streaming(cmd, cwd=config.REPO_PATH, env=_opencode_environment(),
                          timeout=config.AGENT_TIMEOUT_SECONDS)

    output, errors, observed_session = [], [], None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"opencode returned invalid JSON event: {line[:500]!r}") from err
        observed_session = event.get("sessionID") or observed_session
        if event.get("type") == "text":
            part = event.get("part", {})
            text = part.get("text")
            if isinstance(text, str):
                output.append(text)
        elif event.get("type") == "error":
            errors.append(str(event.get("error", "unknown OpenCode error")))

    if proc.returncode != 0 or errors:
        detail = "\n".join(errors) or proc.stderr[-2000:] or proc.stdout[-2000:]
        raise RuntimeError(f"opencode exited {proc.returncode}: {detail}")
    if not observed_session:
        raise RuntimeError(f"opencode output missing sessionID: {proc.stdout[:2000]!r}")
    result = OpenCodeResult(observed_session, "\n".join(output))
    log.info("opencode returned session=%s output=%d chars sentinel=%s",
             result.session_id, len(result.output), result.question is not None)
    log.debug("opencode output:\n%s", result.output)
    return result


def run(prompt: str, contract: bool = True):
    """Start a fresh session. contract=False for one-shot utility calls (PICK, reply
    classifiers) whose only output instruction must be their own JSON contract."""
    if config.AGENT == "claude":
        return claude_runner.run(prompt, contract=contract)
    if config.AGENT == "opencode":
        full = claude_runner.SENTINEL_CONTRACT + "\n\n" + prompt if contract else prompt
        return _opencode(full)
    raise RuntimeError(f"unsupported CODEBOT_AGENT: {config.AGENT!r}")


def resume(session_id: str, prompt: str):
    if config.AGENT == "claude":
        return claude_runner.resume(session_id, prompt)
    if config.AGENT == "opencode":
        try:
            return _opencode(claude_runner.EVIDENCE_CONTRACT + "\n\n" + prompt, session_id)
        except RuntimeError as err:
            if "Session not found" not in str(err):
                raise
            # Sessions can be lost when an in-flight task changes agents or OpenCode's
            # local store is reset. The task artifacts and branch remain authoritative.
            log.warning("OpenCode session %s is unavailable; starting a recovery session", session_id)
            return _opencode(claude_runner.SENTINEL_CONTRACT + "\n\n" +
                             _SESSION_RECOVERY_CONTEXT + "\n\n" + prompt)
    raise RuntimeError(f"unsupported CODEBOT_AGENT: {config.AGENT!r}")
