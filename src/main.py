"""Codebot orchestrator: works the Google Doc backlog one task at a time,
communicating with the user exclusively by email."""
import fcntl
import json
import logging
import re
import signal
import socket
import ssl
import subprocess
import threading
import time
import traceback
from datetime import date
from pathlib import Path

import agent_runner
import config
import drive_client
import evidence
import task_source
import gmail_client
import prompts

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.DEBUG),
                     format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Keep the noisy Google HTTP client at WARNING so our own DEBUG stays readable.
for noisy in ("googleapiclient", "google", "google_auth_httplib2", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("codebot")


# ---------------------------------------------------------------- state

def load_state() -> dict:
    if config.STATE_PATH.exists():
        return json.loads(config.STATE_PATH.read_text())
    return {"state": "IDLE"}


def save_state(state: dict) -> None:
    tmp = config.STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(config.STATE_PATH)


# ---------------------------------------------------------------- helpers

def git(*args: str) -> str:
    log.debug("git %s", " ".join(args))
    proc = subprocess.run(["git", *args], cwd=config.REPO_PATH,
                          capture_output=True, text=True, timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}")
    if proc.stdout.strip():
        log.debug("git %s -> %s", args[0], proc.stdout.strip()[:300])
    return proc.stdout.strip()


def subject(state: dict, phase: str) -> str:
    return f"{config.SUBJECT_PREFIX} {state.get('slug', 'general')} — {phase}"


def email(state: dict, phase: str, body: str, attachments: list[Path] | None = None,
          new_thread: bool = False) -> None:
    thread_id = None if new_thread else state.get("thread_id")
    subj = subject(state, phase)
    log.info("emailing %r (thread=%s, %d attachment(s), %d body chars)",
             subj, thread_id or "new", len(attachments or []), len(body))
    state["thread_id"] = gmail_client.send(subj, body, thread_id, attachments)
    # Snapshot for STATUS replies: lets the user recover what the bot last said (and
    # is therefore waiting on) if the original email was lost or unclear.
    state["last_email"] = {"subject": subj, "body": body, "sent_at": time.time()}
    _note_contact(state)
    names = [Path(a).name for a in (attachments or [])]
    trail(state, phase, body + (f"\n\nAttachments (emailed): {', '.join(names)}" if names else ""))


def trail(state: dict, headline: str, body: str = "") -> None:
    """Append a note to the task's activity trail on the backlog item (issue comment,
    doc comment thread...). Every user-facing email and every silent phase transition
    is noted, so the item doubles as the task's log. Best-effort by design: a tracker
    hiccup is logged and never changes the FSM; nothing is noted without a task."""
    if not config.ACTIVITY_TRAIL or not state.get("item"):
        return
    message = f"[{config.INSTANCE_ID}] {headline}"
    if body:
        message += f"\n\n{body}"
    try:
        ref = task_source.note_activity(state["item"], state.get("item_id"), message,
                                        state.get("trail_ref"))
        if isinstance(ref, str) and ref:
            state["trail_ref"] = ref
    except Exception:  # noqa: BLE001
        log.exception("could not note activity on the backlog item: %r", headline)


def parse_json_reply(text: str) -> dict:
    """Extract the first valid JSON object from the coding agent's output.

    Scans each '{' and uses raw_decode so surrounding prose or later brace-bearing
    text cannot corrupt the match (greedy '{.*}' did).
    """
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"no JSON object in coding-agent output: {text[:500]}")


# ---------------------------------------------------------------- agent log

# One log per task, accumulated in the (git-ignored) data dir while the task runs and
# copied into the archived OpenSpec change at the end — so the reasoning that produced a
# feature is committed next to its proposal, design, and tasks. It is deliberately NOT
# written into the active change dir: the planning phases treat everything under
# openspec/ as their own output, and `openspec validate --strict` runs against the active
# change before we ever get to archive it.
TRANSCRIPT_DIR = config.DATA_DIR / "transcripts"
TRANSCRIPT_NAME = "agent-log.md"


def _transcript_path(state: dict) -> Path:
    """The task's working log, named after the branch (instance id + slug) so concurrent
    instances and a repeated slug never append to each other's file."""
    name = state.get("branch") or state.get("slug") or "general"
    return TRANSCRIPT_DIR / f"{re.sub(r'[^A-Za-z0-9._-]', '-', name)}.md"


def _transcript_append(state: dict, text: str) -> None:
    """Best-effort by design: failing to record a turn must never fail the phase."""
    try:
        path = _transcript_path(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = "" if path.exists() else (
            f"# Agent log — {state.get('slug', 'general')}\n\n"
            f"- Task: {state.get('item', '?')}\n"
            f"- Branch: {state.get('branch', '?')}\n"
            f"- Started: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        with path.open("a") as handle:
            handle.write(header + text)
    except OSError:
        log.exception("could not append to the agent log")


def _transcript_note(state: dict, note: str) -> None:
    """A codebot-side annotation between turns (what we did with the turn's output)."""
    _transcript_append(state, f"\n_codebot: {note}_\n")


def _archive_transcript(state: dict, target: Path) -> None:
    """Copy the working log into the archived change. Best-effort: an otherwise-good
    archive must not fail over the log."""
    source = _transcript_path(state)
    try:
        if not source.is_file():
            log.info("no agent log to archive for %s", state.get("slug"))
            return
        (target / TRANSCRIPT_NAME).write_text(source.read_text())
        log.info("archived agent log (%d bytes) to %s/%s",
                 source.stat().st_size, target.name, TRANSCRIPT_NAME)
    except OSError:
        log.exception("could not archive the agent log")


# Where a phase resumes after a WAIT_STUCK escalation when re-running the phase itself
# makes no sense (its trigger — the user's PR feedback — was consumed).
RESUMABLE_STATE = {"APPLY_PR_FEEDBACK": "WAIT_MERGE", "ADDRESS_PR_THREADS": "WAIT_MERGE"}


def handle_result(state: dict, result, phase: str) -> bool:
    """If the coding agent asked a question, email it and enter WAIT_REPLY. True if waiting.

    Consecutive question round-trips are capped: each round "succeeds" as a tick, so the
    per-state failure budget can never bound this loop — without the cap a session that
    keeps asking (e.g. "what should I work on next?") ping-pongs with the user forever.
    """
    state["session_id"] = result.session_id
    log.debug("[%s] session=%s output=%d chars", phase, result.session_id, len(result.output))
    _transcript_append(state, f"\n## {phase} — {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                              f"Session: `{result.session_id}`\n\n{result.output.strip()}\n")
    question = result.question
    if not question:  # None, or a bare/blank sentinel line — nothing actionable to ask
        state.pop("question_rounds", None)  # phase produced a real result; loop broken
        state.pop("pending_question", None)
        return False
    rounds = state.get("question_rounds", 0) + 1
    state["question_rounds"] = rounds
    if rounds > config.QUESTION_MAX_ROUNDS:
        log.warning("question loop exceeded %d rounds in %s; escalating to WAIT_STUCK",
                    config.QUESTION_MAX_ROUNDS, phase)
        detail = (f"I have asked {rounds - 1} questions in a row during {phase} without "
                  f"completing the phase. The pending question was:\n\n{question}")
        if phase == "APPLY_PR_FEEDBACK":
            detail += ("\n\nNote: if you reply 'retry', please re-send the change request "
                       "you want applied — the original one was consumed.")
        _transcript_note(state, f"{rounds} consecutive questions in {phase}; "
                                f"escalated to WAIT_STUCK")
        _enter_stuck(state, RESUMABLE_STATE.get(phase, phase), detail)
        return True
    attachments = [Path(p) for p in result.attachments if Path(p).exists()]
    log.info("[%s] coding agent asked a question (%d validated attachment(s)); emailing user",
             phase, len(attachments))
    # The agent often puts the substance (a design to approve, options it weighed) ABOVE
    # the sentinel line and only the ask after it; the user needs both to answer.
    preamble = getattr(result, "preamble", "") or ""
    body = f"Task: {state.get('item', '?')}\nPhase: {phase}\n\n"
    if preamble:
        body += f"{preamble}\n\n---\n\n"
    body += f"{question}\n\nReply to this email to continue."
    email(state, f"question during {phase}", body, attachments)
    # Kept so the WAIT_REPLY classifier can judge the reply IN CONTEXT — "yes, that part
    # is done, move on" answers a sub-step question; without the question it reads like
    # a whole-task completion order.
    _transcript_note(state, f"emailed this question to the user "
                            f"({len(attachments)} attachment(s)); waiting for a reply")
    state["pending_question"] = question[:2000]
    state["return_state"] = phase
    state["state"] = "WAIT_REPLY"
    return True


def _parse_completion_contract(output: str, marker: str) -> tuple[dict | None, str | None]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    prefix = marker + ":"
    marked = [line for line in lines if line.startswith(prefix)]
    if output.count(prefix) != 1 or len(marked) != 1:
        return None, f"expected exactly one {marker} contract"
    if not lines or lines[-1] != marked[0]:
        return None, f"{marker} contract must be the final nonblank line"
    try:
        value = json.loads(marked[0][len(prefix):].strip())
    except ValueError:
        return None, f"{marker} contract contains malformed JSON"
    if not isinstance(value, dict):
        return None, f"{marker} contract must contain a JSON object"
    return value, None


def _nonempty_strings(value) -> bool:
    return (isinstance(value, list) and bool(value) and
            all(isinstance(item, str) and item.strip() for item in value))


def _looks_failing(entry: str) -> bool:
    """Whether a "<command>: <result>" entry reports a failure rather than a pass."""
    result = entry.rsplit(":", 1)[-1].strip().lower() if ":" in entry else entry.lower()
    if result.startswith(("pass", "ok", "success", "green")):
        return False
    return bool(re.search(r"\bfail|\berror|\bfatal|\bcrash|timed? ?out|✖|✗", result))


def _failing_summary(commands) -> str:
    """" (failing: ...)" listing the commands the agent itself reported as failing, so the
    rejection reason names the real problem (e.g. 100 lint errors) instead of just
    "status is not pass"."""
    if not isinstance(commands, list):
        return ""
    failing = [c.strip() for c in commands if isinstance(c, str) and c.strip() and _looks_failing(c)]
    return f" (failing: {'; '.join(failing)})" if failing else ""


def parse_quality_gate(output: str) -> tuple[dict | None, str | None]:
    value, reason = _parse_completion_contract(output, "QUALITY_GATE")
    if reason:
        return None, reason
    required = {"status", "commands", "openspec", "tasks"}
    if not required <= set(value) or set(value) - required - {"preexisting"}:
        return None, "quality gate has unexpected or missing fields"
    if value.get("status") != "pass":
        return None, "quality gate status is not pass" + _failing_summary(value.get("commands"))
    if not _nonempty_strings(value.get("commands")):
        return None, "quality gate commands must contain nonempty strings"
    # Failures the agent confirmed on the base branch too (see prompts.VERIFY); the task
    # is not on the hook for them, but they are recorded so the report shows them.
    preexisting = value.get("preexisting", [])
    if not isinstance(preexisting, list) or (preexisting and not _nonempty_strings(preexisting)):
        return None, "quality gate preexisting must be a list of nonempty strings"
    if value.get("openspec") != "pass":
        return None, "OpenSpec validation did not pass"
    match = re.fullmatch(r"(\d+)/(\d+)", value.get("tasks", ""))
    if not match or int(match.group(1)) != int(match.group(2)):
        return None, "OpenSpec tasks are incomplete"
    return value, None


def parse_internal_review(output: str) -> tuple[dict | None, str | None]:
    value, reason = _parse_completion_contract(output, "INTERNAL_REVIEW")
    if reason:
        return None, reason
    if set(value) != {"status", "critical", "important", "tests"}:
        return None, "internal review has unexpected or missing fields"
    if value.get("status") != "pass":
        return None, "internal review status is not pass"
    for severity in ("critical", "important"):
        count = value.get(severity)
        if type(count) is not int or count != 0:
            return None, f"internal review has unresolved {severity} findings"
    if not _nonempty_strings(value.get("tests")):
        return None, "internal review tests must contain nonempty strings"
    return value, None


# Video extensions are the strongest signal on their own (repos essentially never
# legitimately commit one); other hints only count against a path that also names an
# evidence-ish directory/filename, to avoid flagging ordinary repo images/reports.
_EVIDENCE_EXTENSIONS = (".mp4", ".mov", ".webm", ".avi", ".mkv")
_EVIDENCE_PATH_HINTS = ("evidence", "recording")


def _looks_like_evidence(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(_EVIDENCE_EXTENSIONS) or any(h in lower for h in _EVIDENCE_PATH_HINTS)


def _branch_evidence_paths(branch: str, base_branch: str) -> list[str]:
    """Files added/changed on `branch` since it diverged from `base_branch` that look
    like recorded test evidence rather than application code — these must never be
    committed, only emailed (see agent_runner.EVIDENCE_CONTRACT)."""
    diff = git("diff", "--name-only", f"{base_branch}...{branch}")
    return [p for p in diff.splitlines() if _looks_like_evidence(p)]


def _scrub_evidence_from_repo(state: dict, phase: str) -> list[Path] | None:
    """Safety net for when the prompt-level rule against committing evidence still gets
    missed: if evidence-looking files were committed to the branch, have the working
    session remove them from git and re-route them through ATTACH:/email instead.
    Returns extra attachment paths from that corrective turn (possibly empty), or None
    if it asked the user a question instead (caller should treat like handle_result)."""
    paths = _branch_evidence_paths(state["branch"], config.BASE_BRANCH)
    if not paths:
        return []
    log.warning("[%s] evidence-looking file(s) were committed to the repo; asking "
                "the coding agent to remove them and re-route via email instead: %s", phase, paths)
    result = agent_runner.resume(state["session_id"], prompts.render(
        prompts.REMOVE_EVIDENCE_FROM_REPO, branch=state["branch"],
        paths="\n".join(f"- {p}" for p in paths), outbox_dir=str(agent_runner.OUTBOX_DIR)))
    if handle_result(state, result, phase):
        return None
    return [Path(p) for p in result.attachments]


def _collect_attachments(result, e2e_specs: list[str],
                          e2e_kind: str | None) -> list[Path]:
    """Files to attach to a post-task email: whatever the coding agent explicitly pointed to via
    ATTACH: lines in its own (non-question) output, plus whatever the evidence pipeline
    separately records. Claude may have already captured and converted its own evidence
    (e.g. mid-review, outside the dedicated E2E phase) — trust that over re-deriving
    evidence from scratch, which runs in a fresh subprocess and can fail for reasons
    Claude's own sandboxed tool calls didn't hit. Deduped by resolved path in case both
    sources happen to reference the same file."""
    agent_files = [Path(p) for p in result.attachments]
    evidence_files = evidence.record_evidence(e2e_specs, e2e_kind)
    agent_videos = [file for file in agent_files if file.suffix.lower() == ".webm"]
    if agent_videos:
        if evidence_files:
            # The dedicated recorder is canonical when it succeeds; avoid attaching
            # duplicate raw clips from an agent's earlier manual run.
            agent_files = [file for file in agent_files if file not in agent_videos]
        else:
            stitched = evidence.stitch_playwright_clips(agent_videos)
            if stitched:
                agent_files = [file for file in agent_files if file not in agent_videos] + [stitched]
    combined, seen = [], set()
    for f in agent_files + evidence_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            combined.append(f)
    return combined


def _offload_evidence_video(state: dict, attachments: list[Path]) -> tuple[list[Path], str | None]:
    """Upload the evidence video(s) to Drive and take them out of the attachment list;
    returns (remaining attachments, link text or None). Only .mp4 files move — a
    Newman report or an agent screenshot stays attached — and an mp4 whose upload
    failed stays too, so gmail_client attaches it exactly as before (size cap and all).
    Named by branch + timestamp: data/evidence.mp4 is overwritten every round, the
    branch carries the instance name, and a re-finalize must not collide."""
    if not config.EVIDENCE_UPLOAD:
        return attachments, None
    remaining, links = [], []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stem = state.get("branch") or state.get("slug") or "evidence"
    for path in attachments:
        if path.suffix.lower() != ".mp4":
            remaining.append(path)
            continue
        suffix = f"-{len(links) + 1}" if links else ""
        link = drive_client.upload_evidence(path, f"{stem}-{stamp}{suffix}.mp4")
        if link:
            links.append(link)
        else:
            remaining.append(path)
    if not links:
        return remaining, None
    state["evidence_url"] = links[0]
    return remaining, "\n".join(links)


# ---------------------------------------------------------------- capability detection

def _has_e2e_harness() -> bool:
    return (config.REPO_PATH / "e2e" / "run.sh").is_file()


def _has_code_review_workflow() -> bool:
    workflows_dir = config.REPO_PATH / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return False
    for pattern in ("*.yml", "*.yaml"):
        for path in workflows_dir.glob(pattern):
            try:
                text = path.read_text()
            except OSError:
                continue
            # Anchored to column 0: a workflow's own top-level `name:`, not an
            # indented job/step name that happens to say "Code Review" too.
            if re.search(r'^name:\s*["\']?Code Review["\']?\s*$', text, re.MULTILINE):
                return True
    return False


def _e2e_kind_of_present_harness() -> str:
    """"playwright" | "newman" | "unknown", for a harness already known to be present."""
    e2e_dir = config.REPO_PATH / "e2e"
    if (e2e_dir / "playwright.config.ts").is_file():
        return "playwright"
    if any(e2e_dir.rglob("*.postman_collection.json")):
        return "newman"
    return "unknown"


def _has_frontend() -> bool:
    root = config.REPO_PATH
    if (root / "frontend").is_dir() or (root / "angular.json").is_file() or (root / "index.html").is_file():
        return True
    return any(root.glob("vite.config.*")) or any(root.glob("next.config.*"))


def _detect_capabilities(state: dict) -> None:
    """Detect, once per task, whether the target repo has an e2e harness and a Code
    Review workflow, and which e2e tool (Playwright/Newman) is present — or, if no
    harness is present, which one self-healing should request."""
    has_e2e = _has_e2e_harness()
    kind = _e2e_kind_of_present_harness() if has_e2e else (
        "playwright" if _has_frontend() else "newman")
    state["has_e2e_harness"] = has_e2e
    state["has_code_review"] = _has_code_review_workflow()
    state["e2e_kind"] = kind
    log.info("target repo capabilities: e2e_harness=%s kind=%s code_review=%s",
             has_e2e, kind, state["has_code_review"])


# ---------------------------------------------------------------- self-healing

E2E_HARNESS_ITEMS = {
    "playwright": "Set up a Playwright e2e harness (e2e/run.sh + Playwright specs under "
                  "e2e/tests/) so future changes can be gated on it.",
    "newman": "Set up a Newman/Postman e2e harness (e2e/run.sh + collections under "
              "e2e/collections/) so future changes can be gated on it.",
}
CODE_REVIEW_ITEM = (
    "Add a 'Code Review' GitHub Actions workflow that runs the alibaba/open-code-review "
    "(OpenCodeReview) action (https://github.com/alibaba/open-code-review) as the automated "
    "PR reviewer, using an Anthropic API key as its LLM backend. To match coderbot's "
    "automated-review integration exactly: (1) the workflow's top-level `name:` field must be "
    "exactly `Code Review` (NOT the action's own suggested name, `OpenCodeReview PR Review`) "
    "so coderbot's Code Review detection and polling can find it; (2) trigger on pull_request "
    "(or pull_request_target) `opened`, `synchronize`, and `reopened` so a fresh run fires on "
    "every push, including fix-up commits; (3) invoke the action via "
    "`uses: alibaba/open-code-review@<pinned version>` per "
    "https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/integrations/ci.md "
    "(or the action.yml at the repo root), with `llm_use_anthropic: true` and "
    "`llm_url`/`llm_auth_token`/`llm_model` sourced from repo secrets/variables pointing at the "
    "Anthropic API — ask the user for these credentials via NEED_USER_INPUT if they are not "
    "already configured in the repo, rather than guessing; (4) leave `github_token` at its "
    "default (`${{ github.token }}`) and `sticky_summary` at its default (`true`), so feedback "
    "posts as inline PR review comments plus a sticky summary comment under the "
    "`github-actions[bot]` identity — do NOT swap in a custom GitHub App or bot account, since "
    "coderbot only recognizes comments from `github-actions[bot]`; (5) grant "
    "`permissions: contents: read` and `pull-requests: write`.")


def _seed_self_healing_items(state: dict) -> None:
    """Add a backlog item for each piece of missing infrastructure, unless an
    equivalent item is already pending or done."""
    if not state["has_e2e_harness"]:
        if task_source.ensure_item(E2E_HARNESS_ITEMS[state["e2e_kind"]]):
            log.info("self-healing: seeded backlog item for missing e2e harness (%s)",
                     state["e2e_kind"])
    if not state["has_code_review"] and config.SELF_HEAL_CODE_REVIEW:
        if task_source.ensure_item(CODE_REVIEW_ITEM):
            log.info("self-healing: seeded backlog item for missing Code Review workflow")


_EVIDENCE_CONTRACT = (
    " After you're done, an automated evidence step re-runs each new/changed spec/collection "
    "file by NAME ONLY (e.g. `./run.sh your-new-test.spec.ts`), with no extra CLI flags, and "
    "no environment variables beyond what forces recording on (video for Playwright). It must "
    "exercise its real happy path and produce evidence under that exact bare invocation — do "
    "not gate the meaningful assertions behind a custom flag, mode, or env var (e.g. a "
    "`--provider xyz` switch) that this invocation will never pass, and do not have the test "
    "self-skip by default, or no evidence will be captured for the PR.")


_DEMO_TEST_CONTRACT = (
    "\n- ONE of those tests must be a demo test whose title contains the tag `@evidence`. "
    "Codebot records ONLY this test as the video evidence emailed to the user, so it must "
    "show THIS feature working, on its own, as a watchable walkthrough:\n"
    "  - Navigate to where the feature lives and exercise it end-to-end in one continuous flow.\n"
    "  - Before and after each key interaction, make sure the relevant UI is actually visible "
    "in the viewport (e.g. `scrollIntoViewIfNeeded()`) — a correct assertion on an "
    "off-screen element makes a useless video.\n"
    "  - Hold each state that demonstrates the feature's effect on screen for a moment "
    "(e.g. `page.waitForTimeout(1000)`) so a human watching the video can see it.\n"
    "  - Keep unrelated setup minimal and off-camera where possible; assert the visible outcome.\n"
    "  - NARRATE THE VIDEO ON SCREEN. A silent recording of clicks does not read as evidence "
    "to the person watching it, so the video must explain itself without any accompanying text:\n"
    "    - Open with a title card held for ~3s stating the backlog item / feature name and, in "
    "one or two lines, what the viewer is about to see and what would prove the feature works.\n"
    "    - Before each key interaction, show a caption naming the step, what is about to happen, "
    "and why it is evidence (e.g. \"Step 2/4 - saving the form; the new title must appear in the "
    "header, which was impossible before this change\"). Hold the caption long enough to read "
    "(~2s) and keep it visible while the step runs.\n"
    "    - After the decisive step, show a closing caption that names the visible outcome the "
    "viewer should be looking at and states that it is the implemented behavior.\n"
    "    - Implement the captions as a DOM overlay you inject into the page (e.g. a fixed-position, "
    "high-contrast, high z-index banner added via `page.evaluate`, wrapped in a small local "
    "`narrate(page, text)` helper) so they are captured in the recorded video. Captions must never "
    "cover the UI the step is demonstrating, and must never be asserted on or otherwise affect "
    "what the test verifies — the real assertions stay on the application's own UI.")


def _e2e_note(state: dict) -> str:
    if not state.get("has_e2e_harness"):
        return ("- No e2e harness exists in this repo yet; verify the change using your own "
                "judgment (existing test suites, manual checks, etc.) instead of writing e2e "
                "tests.")
    if state.get("e2e_kind") == "newman":
        return ("- Every user-facing feature MUST include comprehensive Postman collections "
                "under e2e/collections/, run via Newman (they must pass)." + _EVIDENCE_CONTRACT)
    return ("- Every user-facing feature MUST include comprehensive Playwright e2e tests in "
            "e2e/tests/ (they must pass)." + _EVIDENCE_CONTRACT + _DEMO_TEST_CONTRACT)


def _e2e_report_note(state: dict) -> str:
    if not state.get("has_e2e_harness"):
        return "End with a summary of what was implemented and how you verified it."
    return ("End with a summary of what was implemented and the list of new/changed e2e test "
            "files (one per line, prefixed with `E2E_SPEC: `).")


# ---------------------------------------------------------------- phases

def do_pick(state: dict) -> None:
    # Only tracked, uncommitted changes matter — untracked files (e.g. host-side
    # git-ignored config not excluded inside the container) don't block a checkout.
    if git("status", "--porcelain", "--untracked-files=no"):
        email(state, "blocked: dirty working tree",
              "The repo working tree has uncommitted changes; codebot will not start a "
              "new task. Clean it up and reply to this email to retry.", new_thread=True)
        state["state"] = "WAIT_CLEAN"
        return
    # Sync to the base branch before detecting target-repo capabilities and seeding
    # any self-healing item, so both reflect its actual current state rather than
    # whatever branch was last checked out.
    git("checkout", config.BASE_BRANCH)
    git("pull", "--ff-only")
    _detect_capabilities(state)
    _seed_self_healing_items(state)
    requested = sorted((h for h in _load_holds() if h.get("requested")),
                       key=lambda h: h.get("requested_at", 0))
    if requested:
        _resume_held_task(state, requested[0])
        if state["state"] != "IDLE":
            return
    items = task_source.list_pending_items()
    log.info("backlog has %d pending item(s)", len(items))
    if not items:
        log.info("no pending items; staying idle")
        state["state"] = "IDLE"
        return
    # A claim of ours that outlived state.json (e.g. the data dir was rebuilt) is
    # resumed before anything new is started, so no task is left claimed but unworked.
    mine = [i for i in items if i.get("claimed_by_me")]
    if mine:
        log.info("resuming from %d item(s) already claimed by this instance", len(mine))
        items = mine
    else:
        items = prioritize_items(items)
    result = agent_runner.run(prompts.render(
        prompts.PICK, project=config.PROJECT_NAME, items=render_items(items)),
        contract=False)
    choice = parse_json_reply(result.output)
    if not choice.get("item") or not choice.get("slug"):
        raise ValueError(f"PICK output missing item/slug: {choice!r}")
    chosen = next((i for i in items
                   if task_source.normalize(i["text"]) == task_source.normalize(choice["item"])),
                  None)
    if chosen is None:
        # The bullet's own text is the identity mark_done matches on later, so a paraphrase
        # (or a sub-bullet picked as an item) must not become the task. Fail the tick; PICK
        # runs again next time.
        raise ValueError(f"PICK chose text that is not a pending item: {choice['item'][:200]!r}")
    # Claim the item in the backlog BEFORE any local work: the claim write is what
    # keeps two instances off the same task. Losing the race just means repicking.
    if not task_source.claim_task(chosen["text"], chosen.get("id") or None):
        log.info("item was claimed by another instance meanwhile; repicking next tick: %r",
                 chosen["text"][:80])
        return  # stay IDLE
    log.info("coding agent picked %r (slug=%s, %d clarification line(s), %d screenshot(s)): %s",
             chosen["text"][:80], choice["slug"], len(chosen["detail"].splitlines()),
             len(chosen.get("images", [])), choice.get("reason", ""))
    state.update(item=chosen["text"], item_detail=chosen["detail"],
                 item_images=chosen.get("images", []),
                 item_id=chosen.get("id") or None, item_url=chosen.get("url") or None,
                 slug=choice["slug"], thread_id=None)
    # Flat prefix (no slash): a "codebot/<slug>" branch would collide with the
    # existing "codebot" branch in git's ref namespace (file-vs-directory, exit 128).
    branch = f"{config.INSTANCE_ID}-{choice['slug']}"
    # -B is idempotent: if do_pick is retried after the branch was already created
    # (state not yet persisted), reset it from the base branch rather than failing on "-b".
    git("checkout", "-B", branch)
    state["branch"] = branch
    # The branch's starting point: later phases measure overreach against it.
    state["base_sha"] = git("rev-parse", "HEAD")
    state["state"] = "EXPLORING"
    log.info("picked %r -> %s", choice["item"], branch)
    trail(state, f"Picked this item; working on branch {branch}", choice.get("reason", ""))


def prioritize_items(items: list[dict]) -> list[dict]:
    """Honor the user's Codebot[n] ordering tags: when any pending item carries one,
    only the item(s) with the LOWEST number are offered to PICK, so tagged work is done
    first and in the written order; untagged items wait until no tagged item remains."""
    tagged = [i for i in items if i.get("priority") is not None]
    if not tagged:
        return items
    lowest = min(i["priority"] for i in tagged)
    chosen = [i for i in tagged if i["priority"] == lowest]
    log.info("%d item(s) carry Codebot[n] tags; offering the %d tagged Codebot[%d]",
             len(tagged), len(chosen), lowest)
    return chosen


def render_items(items: list[dict]) -> str:
    """The backlog as a nested bullet list: one line per task, clarifications indented."""
    lines = []
    for item in items:
        lines.append(f"- {item['text']}")
        if item.get("detail"):
            lines.append(item["detail"])
    return "\n".join(lines)


def render_images(paths: list[str]) -> str:
    """The prompt block pointing the session at the item's screenshots ("" when none)."""
    existing = [p for p in paths if Path(p).exists()]
    if len(existing) < len(paths):
        log.warning("%d of %d item screenshot(s) missing on disk",
                    len(paths) - len(existing), len(paths))
    if not existing:
        return ""
    log.info("EXPLORE prompt includes %d screenshot(s): %s", len(existing), existing)
    return ("\nThe user attached screenshot(s) to this item in the backlog. They show "
            "the exact UI/behavior the item refers to — view EACH one with the Read tool "
            "before drawing conclusions:\n"
            + "\n".join(f"- {p}" for p in existing) + "\n")


def do_explore(state: dict) -> None:
    result = agent_runner.run(prompts.render(
        prompts.EXPLORE, project=config.PROJECT_NAME, branch=state["branch"], item=state["item"],
        detail=state.get("item_detail", ""),
        images=render_images(state.get("item_images", []))))
    if handle_result(state, result, "EXPLORING"):
        return
    _undo_premature_work(state, "EXPLORING")
    state["state"] = "PROPOSING"


def _undo_premature_work(state: dict, phase: str) -> str:
    """Revert work that goes beyond a planning phase (EXPLORING/PROPOSING must not
    implement, commit, or switch branches). Openspec change artifacts are the phases'
    legitimate output and are left alone. Returns a note for the user ('' when clean).

    Best-effort by design: a cleanup error must never fail the phase, so problems are
    reported in the note instead of raised."""
    notes = []
    base_branch = config.BASE_BRANCH
    try:
        current = git("rev-parse", "--abbrev-ref", "HEAD")
        base = state.get("base_sha") or git("merge-base", "HEAD", base_branch)
        branch = state.get("branch")
        if branch and current != branch:
            # The session wandered off the task branch (worst case: committed on the local
            # base branch). -B recreates/resets the task branch at its base even if the
            # session deleted it; -f discards conflicting tracked changes — premature by
            # definition in a planning phase.
            notes.append(f"the session left the checkout on '{current}'; "
                         f"reset '{branch}' to its base and returned to it")
            git("checkout", "-f", "-B", branch, base)
            if current == base_branch:
                try:
                    upstream = git("rev-parse", f"origin/{base_branch}")
                    if git("rev-parse", base_branch) != upstream:
                        git("branch", "-f", base_branch, upstream)
                        notes.append(f"local {base_branch} had premature commits; reset it "
                                     f"to origin/{base_branch}")
                except Exception:  # noqa: BLE001 — e.g. no origin/<base> ref cached
                    notes.append(f"could not verify local {base_branch} against "
                                 f"origin/{base_branch} — please check it manually")
        else:
            ahead = git("rev-list", "--count", f"{base}..HEAD") or "0"
            if ahead != "0":
                notes.append(f"undid {ahead} premature commit(s)")
                git("reset", "--soft", base)
        # -z: NUL-separated and never C-quoted, so paths with spaces/UTF-8 parse exactly
        # (the quoted form broke both the openspec/ prefix check and the git commands).
        entries = git("status", "--porcelain", "-z", "--untracked-files=no").split("\0")
        offending = []
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if not entry:
                continue
            code, path = entry[:2], entry[3:]
            paths = [path]  # rename/copy: [destination, source] — source follows as its
            if "R" in code or "C" in code:  # own NUL-separated record
                paths.append(entries[i])
                i += 1
            if all(p.startswith("openspec/") for p in paths):
                continue
            offending.append((code, paths))
        for code, paths in offending:
            if len(paths) == 2:
                dest, src = paths
                if not src.startswith("openspec/"):
                    git("checkout", "HEAD", "--", src)  # undo the deletion side
                if not dest.startswith("openspec/"):  # never delete an openspec artifact
                    git("rm", "-f", "--ignore-unmatch", "--", dest)
            elif "A" in code:  # staged addition: no base version to restore
                git("rm", "-f", "--", paths[0])
            else:
                git("checkout", "HEAD", "--", paths[0])
        if offending:
            notes.append("discarded premature changes outside openspec/: "
                         + ", ".join(p for _c, ps in offending for p in ps))
    except Exception as err:  # noqa: BLE001 — hygiene must not break the phase
        log.exception("premature-work cleanup failed")
        notes.append(f"tried to revert premature work but hit an error: {err}")
    if not notes:
        return ""
    note = (f"Note: I detected work beyond the {phase} phase and cleaned it up "
            f"({'; '.join(notes)}). Implementation starts only after your approval.")
    log.warning("%s", note)
    return note


def do_propose(state: dict) -> None:
    result = agent_runner.resume(state["session_id"], prompts.render(
        prompts.PROPOSE, slug=state["slug"], e2e_note=_e2e_note(state)))
    if handle_result(state, result, "PROPOSING"):
        return
    note = _undo_premature_work(state, "PROPOSING")
    email(state, "proposal for review",
          f"Task: {state['item']}\n\n{result.output}\n\n" + (f"{note}\n\n" if note else "")
          + "Reply with your approval or requested changes.")
    state["state"] = "WAIT_APPROVAL"


def do_approval_reply(state: dict, reply: str) -> None:
    # Never let the autonomous working session self-declare approval. Classify the
    # user's own words with a fresh, dedicated session (like do_merge_reply) and only
    # advance on an explicit go-ahead; anything else keeps us waiting for real approval.
    verdict = parse_json_reply(
        agent_runner.run(prompts.render(prompts.CLASSIFY_APPROVAL_REPLY, reply=reply),
                         contract=False).output)
    action = verdict.get("action")
    log.info("classified approval reply as action=%r", action)
    if action not in ("approve", "changes", "abort", "complete"):
        email(state, "clarification needed",
              f"I could not tell whether your reply approves the proposal, requests "
              f"changes, marks the task complete, or aborts:\n\n{reply}\n\nPlease reply "
              "again with an explicit approval, the changes you want, 'complete', or 'abort'.")
        return  # stay in WAIT_APPROVAL
    if action == "abort":
        _abort_and_reset(state, "Got it — I'm stopping this task and resetting to a clean slate.")
        return
    if action == "complete":
        _finish_task(state, "You asked me to mark this task complete with no further work.",
                     reset_repo=True)
        return
    if action == "approve":
        trail(state, "Proposal approved by the user", reply)
        state["state"] = "IMPLEMENTING"
        return
    # changes: revise the proposal in the working session and go back to waiting.
    result = agent_runner.resume(
        state["session_id"],
        prompts.render(prompts.REVISE_PROPOSAL, feedback=verdict.get("feedback", ""), slug=state["slug"]))
    if handle_result(state, result, "PROPOSING"):
        return
    note = _undo_premature_work(state, "PROPOSING")
    email(state, "revised proposal", result.output + "\n\n" + (f"{note}\n\n" if note else "")
          + "Reply with your approval or further changes.")
    state["state"] = "WAIT_APPROVAL"


def do_implement(state: dict) -> None:
    result = agent_runner.resume(
        state["session_id"],
        prompts.render(prompts.IMPLEMENT, slug=state["slug"], branch=state["branch"],
                       e2e_note=_e2e_note(state), e2e_report_note=_e2e_report_note(state)))
    if handle_result(state, result, "IMPLEMENTING"):
        return
    if _scrub_evidence_from_repo(state, "IMPLEMENTING") is None:
        return
    state["e2e_specs"] = evidence.reported_specs(result.output)
    log.info("implementation reported %d e2e spec(s): %s",
             len(state["e2e_specs"]), state["e2e_specs"])
    if not state["e2e_specs"] and state.get("has_e2e_harness"):
        log.warning("no E2E_SPEC lines in implementation output — feature may lack tests")
    state["e2e_round"] = 0
    state["verify_round"] = 0
    state["state"] = "VERIFYING"
    trail(state, "Implementation complete; verifying")


GATE_REPORT_MAX_CHARS = 3000
GATE_NOTES_MAX_CHARS = 2500

# Contract fields that hold "<command>: <result>" entries, per gate marker.
_GATE_CHECK_FIELDS = {"QUALITY_GATE": ("commands", "preexisting"),
                      "INTERNAL_REVIEW": ("tests",)}


def _gate_report(output: str, marker: str) -> str:
    """A human-readable account of a rejected gate round for the retry prompt and the
    stuck email: every check the agent reported (failing ones first), the contract's
    other fields, then the agent's own notes (the prose before the contract). The bare
    contract JSON is deliberately NOT what the user sees — a live incident emailed only
    "status is not pass" while the real story (100 lint errors) sat in a JSON list."""
    prefix = marker + ":"
    contract_lines = [line.strip() for line in output.splitlines()
                      if line.strip().startswith(prefix)]
    notes = "\n".join(line for line in output.splitlines()
                      if not line.strip().startswith(prefix)).strip()
    parts: list[str] = []
    value = None
    if contract_lines:
        try:
            value = json.loads(contract_lines[-1][len(prefix):].strip())
        except ValueError:
            value = None
    if isinstance(value, dict):
        checks = []
        for field in _GATE_CHECK_FIELDS.get(marker, ()):
            entries = value.get(field)
            if isinstance(entries, list):
                label = "" if field in ("commands", "tests") else f" [{field}]"
                checks += [(str(e).strip() + label) for e in entries if str(e).strip()]
        if checks:
            failing = [c for c in checks if _looks_failing(c)]
            passing = [c for c in checks if not _looks_failing(c)]
            parts.append("Checks the agent reported (failing first):\n"
                         + "\n".join(f"- {c}" for c in failing + passing))
        others = {k: v for k, v in value.items()
                  if k not in _GATE_CHECK_FIELDS.get(marker, ()) and k != "status"}
        if others:
            parts.append("Other contract fields: "
                         + ", ".join(f"{k}={json.dumps(v)}" for k, v in others.items()))
    elif contract_lines:
        parts.append("Contract line as emitted (malformed): " + contract_lines[-1][:500])
    if notes:
        tail = notes[-GATE_NOTES_MAX_CHARS:]
        if len(notes) > GATE_NOTES_MAX_CHARS:
            tail = "[...]\n" + tail
        parts.append("Agent's notes:\n" + tail)
    return "\n\n".join(parts)[:GATE_REPORT_MAX_CHARS + GATE_NOTES_MAX_CHARS]


def _gate_failed(state: dict, phase: str, counter: str, reason: str, report: str = "") -> None:
    state[counter] = state.get(counter, 0) + 1
    # Fed back into the next round's prompt (and the stuck email): a retry that repeats
    # the identical prompt just gets the identical failing report again.
    state[f"{counter}_feedback"] = {"reason": reason, "report": report}
    log.warning("%s result rejected (round %d/%d): %s", phase, state[counter],
                config.QUALITY_GATE_MAX_ROUNDS, reason)
    if state[counter] < config.QUALITY_GATE_MAX_ROUNDS:
        state["state"] = phase
        return
    label = phase.lower().replace('_', ' ')
    body = (f"Task: {state['item']}\n\nThe {label} gate has failed {state[counter]} times. "
            f"Latest reason: {reason}\n\n")
    if report:
        body += f"{report}\n\n"
    body += ("Reply with guidance to continue — e.g. tell the agent to fix a failure, or that a "
             "failure is pre-existing on the base branch (it will confirm that there and "
             "report it as pre-existing).")
    email(state, f"{label} stuck - needs your help", body)
    state["return_state"] = phase
    state["state"] = "WAIT_REPLY"


def _gate_feedback(state: dict, counter: str) -> str:
    """The rejection notice to prepend to a gate prompt, or "" on a fresh first round."""
    feedback = state.get(f"{counter}_feedback")
    if not state.get(counter) or not isinstance(feedback, dict):
        return ""
    return prompts.render(prompts.GATE_FEEDBACK, round=state[counter],
                          max=config.QUALITY_GATE_MAX_ROUNDS,
                          reason=feedback.get("reason", ""), report=feedback.get("report", ""))


def _verify_prompt(state: dict) -> str:
    return (_gate_feedback(state, "verify_round")
            + prompts.render(prompts.VERIFY, slug=state["slug"], base=config.BASE_BRANCH))


def _internal_review_prompt(state: dict) -> str:
    return (_gate_feedback(state, "review_gate_round")
            + prompts.render(prompts.INTERNAL_REVIEW, slug=state["slug"]))


def _complete_verify(state: dict, result) -> None:
    if handle_result(state, result, "VERIFYING"):
        return
    parsed, reason = parse_quality_gate(result.output)
    if parsed is None:
        _gate_failed(state, "VERIFYING", "verify_round", reason,
                     _gate_report(result.output, "QUALITY_GATE"))
        return
    try:
        slug = _validated_slug(state.get("slug"))
        _run_checked(["openspec", "validate", slug, "--strict", "--no-interactive"])
        instructions = json.loads(_run_checked([
            "openspec", "instructions", "apply", "--change", slug, "--json",
        ]))
        progress = instructions.get("progress") if isinstance(instructions, dict) else None
        if not isinstance(progress, dict) or instructions.get("state") != "all_done":
            raise ValueError("OpenSpec apply state is not all_done")
        total = progress.get("total")
        complete = progress.get("complete")
        remaining = progress.get("remaining")
        if any(type(value) is not int for value in (total, complete, remaining)) or \
                remaining != 0 or complete != total:
            raise ValueError("OpenSpec apply progress is incomplete")
    except Exception as error:
        _gate_failed(state, "VERIFYING", "verify_round", str(error),
                     _gate_report(result.output, "QUALITY_GATE"))
        return
    state.pop("verify_round", None)
    state.pop("verify_round_feedback", None)
    state["review_gate_round"] = 0
    state["state"] = "INTERNAL_REVIEW"
    trail(state, "Verification passed; running internal review")


def do_verify(state: dict) -> None:
    result = agent_runner.resume(state["session_id"], _verify_prompt(state))
    _complete_verify(state, result)


def _complete_internal_review(state: dict, result) -> None:
    if handle_result(state, result, "INTERNAL_REVIEW"):
        return
    parsed, reason = parse_internal_review(result.output)
    if parsed is None:
        _gate_failed(state, "INTERNAL_REVIEW", "review_gate_round", reason,
                     _gate_report(result.output, "INTERNAL_REVIEW"))
        return
    state.pop("review_gate_round", None)
    state.pop("review_gate_round_feedback", None)
    state["state"] = "E2E" if state.get("has_e2e_harness") else "ARCHIVING"
    trail(state, "Internal review passed; " +
          ("running the e2e suite" if state.get("has_e2e_harness") else "archiving the change"))


def do_internal_review(state: dict) -> None:
    result = agent_runner.resume(state["session_id"], _internal_review_prompt(state))
    _complete_internal_review(state, result)


def _tracked_snapshot() -> tuple[str, str]:
    return (git("rev-parse", "HEAD"),
            git("status", "--porcelain", "--untracked-files=no"))


def _finish_e2e_repair(state: dict) -> None:
    before = (state.pop("e2e_repair_head"), state.pop("e2e_repair_status"))
    if _tracked_snapshot() != before:
        state["verify_round"] = 0
        state["state"] = "VERIFYING"
    else:
        state["state"] = "E2E"


def do_e2e(state: dict) -> None:
    if "e2e_repair_head" in state and "e2e_repair_status" in state:
        _finish_e2e_repair(state)
        if state["state"] != "E2E":
            return
    if not state.get("has_e2e_harness"):
        log.info("no e2e harness detected for this task; skipping the e2e gate")
        state["state"] = "ARCHIVING"
        return
    log.info("running e2e suite (e2e/run.sh)")
    passed, output = evidence.run_suite()
    if not passed:
        state["e2e_round"] = state.get("e2e_round", 0) + 1
        log.warning("e2e suite FAILED (round %d/%d); resuming session to fix. Tail:\n%s",
                    state["e2e_round"], config.E2E_MAX_ROUNDS, output[-1500:])
        trail(state, f"e2e suite failed (round {state['e2e_round']}/{config.E2E_MAX_ROUNDS})",
              output[-1500:])
        if state["e2e_round"] > config.E2E_MAX_ROUNDS:
            log.warning("e2e round limit (%d) reached; asking user for help instead of retrying",
                        config.E2E_MAX_ROUNDS)
            email(state, "e2e suite stuck — needs your help",
                  f"Task: {state['item']}\n\nThe e2e suite has failed {config.E2E_MAX_ROUNDS} "
                  "times in a row and I could not fix it myself (this is often caused by "
                  "something outside the code, e.g. a stuck process/port left over from a "
                  f"prior run). Latest failure output:\n\n{output[-3000:]}\n\n"
                  "Please investigate, then reply with guidance (or tell me what to try) "
                  "to continue.")
            state["return_state"] = "E2E"
            state["state"] = "WAIT_REPLY"
            return
        state["e2e_repair_head"], state["e2e_repair_status"] = _tracked_snapshot()
        save_state(state)
        result = agent_runner.resume(state["session_id"], prompts.render(prompts.FIX_E2E, output=output))
        if handle_result(state, result, "E2E"):
            return
        _finish_e2e_repair(state)
        return  # loop re-enters E2E and re-runs the suite
    log.info("e2e suite PASSED")
    state["e2e_round"] = 0
    state["state"] = "ARCHIVING"
    trail(state, "e2e suite passed; archiving the change")


def _run_checked(command: list[str]) -> str:
    proc = subprocess.run(command, cwd=config.REPO_PATH, capture_output=True, text=True, timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"{' '.join(command)} exited {proc.returncode}: {detail}")
    return proc.stdout.strip()


def _validated_slug(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError("change slug must be safe kebab-case")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("dated change slug must include a kebab-case name")
    dated = re.match(r"^(\d{4}-\d{2}-\d{2})-", value)
    if dated:
        try:
            date.fromisoformat(dated.group(1))
        except ValueError as error:
            raise ValueError("change slug has an invalid date prefix") from error
    return value


def _validated_archive_path(value, slug: str) -> Path:
    if not isinstance(value, str):
        raise ValueError("archive path must be a relative string")
    relative = Path(value)
    if relative.is_absolute() or relative.parts[:3] != ("openspec", "changes", "archive") or \
            len(relative.parts) != 4:
        raise ValueError("archive path must be a direct child of openspec/changes/archive")
    name = relative.name
    if re.match(r"^\d{4}-\d{2}-\d{2}-", slug):
        if name != slug:
            raise ValueError("archive path does not match the dated change slug")
    else:
        match = re.fullmatch(rf"(\d{{4}}-\d{{2}}-\d{{2}})-{re.escape(slug)}", name)
        if not match:
            raise ValueError("archive path does not match the change slug")
        try:
            date.fromisoformat(match.group(1))
        except ValueError as error:
            raise ValueError("archive path has an invalid date prefix") from error

    repo = config.REPO_PATH.resolve()
    archive_root = repo / "openspec" / "changes" / "archive"
    target = (config.REPO_PATH / relative).resolve()
    if target.parent != archive_root:
        raise ValueError("archive path resolves outside openspec/changes/archive")
    return target


def _archive_target(state: dict) -> Path:
    slug = _validated_slug(state.get("slug"))
    if state.get("archive_path"):
        return _validated_archive_path(state["archive_path"], slug)
    active = config.REPO_PATH / "openspec" / "changes" / slug
    archive_root = config.REPO_PATH / "openspec" / "changes" / "archive"
    if archive_root.resolve() != config.REPO_PATH.resolve() / "openspec" / "changes" / "archive":
        raise ValueError("archive root resolves outside the repository")
    matches = list(archive_root.glob(f"????-??-??-{slug}")) if archive_root.is_dir() else []
    if not active.exists() and len(matches) == 1:
        target = matches[0]
    elif not active.exists() and len(matches) > 1:
        raise RuntimeError(f"multiple archives match change {slug}")
    else:
        name = slug if re.match(r"^\d{4}-\d{2}-\d{2}-", slug) else f"{date.today():%Y-%m-%d}-{slug}"
        target = archive_root / name
    relative = str(target.relative_to(config.REPO_PATH))
    target = _validated_archive_path(relative, slug)
    state["archive_path"] = relative
    save_state(state)
    return target


def _archive_failed(state: dict, error: Exception) -> None:
    state["archive_error"] = str(error)
    state["archive_round"] = state.get("archive_round", 0) + 1
    log.warning("archive failed (round %d/%d): %s", state["archive_round"],
                config.ARCHIVE_MAX_ROUNDS, error)
    if state["archive_round"] < config.ARCHIVE_MAX_ROUNDS:
        state["state"] = "ARCHIVING"
        return
    email(state, "OpenSpec archival stuck - needs your help",
          f"Task: {state['item']}\n\nArchival failed {state['archive_round']} times. "
          f"Latest error: {error}\n\nReply with guidance to retry.")
    state["return_state"] = "ARCHIVING"
    state["state"] = "WAIT_REPLY"


def _unrelated_archive_changes(state: dict, status: str) -> list[str]:
    """Paths in a `git status --porcelain` listing outside the archive's outputs.

    `git()` strips its output, which removes the leading status column of the first
    line (" D path" -> "D path"), so parse each line by the first whitespace after the
    XY status field instead of a fixed offset.
    """
    allowed = (
        "openspec/specs",
        f"openspec/changes/{state['slug']}",
        state["archive_path"],
    )
    unrelated = []
    for line in status.splitlines():
        if not line.strip():
            continue
        match = re.match(r"^ ?[A-Z?!]{1,2} (.*)$", line)
        rest = match.group(1) if match else line
        for path in rest.split(" -> "):
            path = path.strip().strip('"')
            if not any(path == root or path.startswith(root + "/") for root in allowed):
                unrelated.append(path)
    return unrelated


def _validate_archived_change(target: Path) -> None:
    """Strict-validate only the change we just archived.

    `openspec validate --archived` has no per-change form and checks every archived
    change in the repo, so a stale archive with an unticked task would block every
    future task forever. Parse the JSON report and fail only on our own change.
    """
    command = ["openspec", "validate", "--archived", "--strict", "--no-interactive", "--json"]
    proc = subprocess.run(command, cwd=config.REPO_PATH, capture_output=True, text=True,
                          timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    try:
        items = json.loads(proc.stdout)["items"]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise TypeError("items must be a list of objects")
    except (ValueError, KeyError, TypeError) as error:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(
            f"{' '.join(command)} exited {proc.returncode} with an unreadable report: {detail}"
        ) from error
    mine = [item for item in items if item.get("id") == target.name]
    if not mine:
        raise RuntimeError(f"archived change {target.name} is missing from the validation report")
    if not all(item.get("valid") is True for item in mine):
        issues = "; ".join(
            f"{issue.get('path', '?')}: {issue.get('message', '?')}"
            for item in mine for issue in item.get("issues", []) if isinstance(issue, dict)
        ) or "no details reported"
        raise RuntimeError(f"archived change {target.name} failed strict validation: {issues}")
    stale = sorted(item.get("id", "?") for item in items
                   if item.get("id") != target.name and item.get("valid") is not True)
    if stale:
        log.warning("ignoring pre-existing invalid archived changes: %s", ", ".join(stale))


def do_archive(state: dict) -> None:
    try:
        target = _archive_target(state)
        active = config.REPO_PATH / "openspec" / "changes" / state["slug"]
        if active.exists() and target.exists():
            raise RuntimeError("active change and expected archive both exist")
        if active.exists():
            if git("status", "--porcelain", "--untracked-files=no"):
                raise RuntimeError("tracked working tree must be clean before archival")
            if git("status", "--porcelain", "--untracked-files=all", "--", "openspec/"):
                raise RuntimeError("OpenSpec tree must be clean before archival")
            _run_checked(["openspec", "archive", state["slug"], "-y", "--json"])
        elif not target.is_dir():
            raise RuntimeError("active change and expected archive are both absent")
        if not target.is_dir():
            raise RuntimeError("archive command did not create the expected archive")

        _run_checked(["openspec", "validate", "--specs", "--strict", "--no-interactive"])
        _validate_archived_change(target)
        # After validation, so an unrecognized extra file can never fail strict
        # validation of the change itself; before the commit below, whose path list
        # already covers everything under the archive dir.
        _archive_transcript(state, target)
        status = git("status", "--porcelain", "--untracked-files=all")
        unrelated = _unrelated_archive_changes(state, status) if status else []
        if unrelated:
            raise RuntimeError("archival produced unrelated tracked changes: "
                               + ", ".join(unrelated[:10]))
        if status:
            paths = ("openspec/specs", f"openspec/changes/{state['slug']}",
                     state["archive_path"])
            git("add", "-A", "--", *paths)
            git("commit", "-m", "chore: archive OpenSpec change", "--", *paths)
        state.pop("archive_round", None)
        state.pop("archive_error", None)
        state["state"] = "OPEN_PR"
        trail(state, "OpenSpec change archived; opening the PR")
    except Exception as error:
        _archive_failed(state, error)


def _https_url(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"https://\S+", value.strip()):
        raise RuntimeError(f"expected one HTTPS URL, got: {value!r}")
    return value.strip()


def _resume_archiving(state: dict, reason: str) -> None:
    log.warning("OPEN_PR archival precondition failed: %s", reason)
    state.pop("pr_url", None)
    state.pop("pr_summary", None)
    state["archive_error"] = reason
    state["archive_round"] = 0
    state["state"] = "ARCHIVING"


# GitHub rejects pull-request titles longer than this (GraphQL "Title is too long").
PR_TITLE_HARD_MAX = 256
# What we aim for: a one-line summary, not the backlog bullet.
PR_TITLE_TARGET = 72
_CODEBOT_TAG = re.compile(r"\bcode\s*bot\s*\[\s*\d+\s*\]\s*:?", re.IGNORECASE)


def _clamp_pr_title(title, limit: int = PR_TITLE_HARD_MAX) -> str:
    """One line, tags stripped, never longer than `limit` (cut on a word, with an ellipsis)."""
    text = " ".join(str(title or "").split())
    text = _CODEBOT_TAG.sub("", text).strip(" -:—–")
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:.-—–(")
    return (cut or text[:limit - 1]) + "…"


def _fallback_pr_title(item: str) -> str:
    """Deterministic summary of a backlog bullet: its first clause, capped at the target.
    Used when the coding agent cannot produce a title (or produces an unusable one)."""
    text = _clamp_pr_title(item)
    for sep in (";", ":", ". ", ", que ", ", which ", " — ", " - "):
        head = text.split(sep, 1)[0].strip()
        if 12 <= len(head) < len(text):
            text = head
            break
    return _clamp_pr_title(text, PR_TITLE_TARGET) or "Codebot change"


def _pr_title(state: dict) -> str:
    """The title used for `gh pr create`: persisted in state["pr_title"] so retries reuse
    it, and regenerated when the user gives guidance (state["pr_title_guidance"]) from a
    WAIT_STUCK reply. Always within GitHub's limit, whatever the agent returns."""
    cached = state.get("pr_title")
    if isinstance(cached, str) and cached.strip():
        return _clamp_pr_title(cached)
    item = state["item"]
    guidance = state.get("pr_title_guidance") or ""
    short = _clamp_pr_title(item)
    if not guidance and len(short) <= PR_TITLE_TARGET:
        title = short
    else:
        title = ""
        try:
            prompt = prompts.render(
                prompts.PR_TITLE, item=item,
                guidance=prompts.render(prompts.PR_TITLE_GUIDANCE, guidance=guidance)
                if guidance else "")
            reply = parse_json_reply(agent_runner.run(prompt, contract=False).output)
            title = _clamp_pr_title(reply.get("title"))
        except Exception:
            log.exception("PR title generation failed; using the fallback title")
        if not title or title == short:
            title = _fallback_pr_title(item)
    title = _clamp_pr_title(title)
    if not title:
        title = _fallback_pr_title(item)
    state["pr_title"] = title
    log.info("PR title: %r", title)
    return title


def do_open_pr(state: dict) -> None:
    if not state.get("archive_path"):
        state["verify_round"] = 0
        state.pop("review_gate_round", None)
        state["state"] = "VERIFYING"
        return
    slug = _validated_slug(state.get("slug"))
    target = _validated_archive_path(state["archive_path"], slug)
    reference = str(target.relative_to(config.REPO_PATH.resolve()))
    active = config.REPO_PATH / "openspec" / "changes" / slug
    if not target.is_dir():
        _resume_archiving(state, "validated archive directory is missing")
        return
    if active.exists():
        _resume_archiving(state, "active OpenSpec change still exists")
        return
    if git("status", "--porcelain", "--untracked-files=all", "--", "openspec/"):
        _resume_archiving(state, "OpenSpec tree is dirty before PR creation")
        return
    if not git("ls-tree", "-r", "--name-only", "HEAD", "--", reference).strip():
        _resume_archiving(state, "archive is not committed in HEAD")
        return
    body = f"Implements: {state['item']}\n\nOpenSpec archive: `{reference}`"
    if state.get("item_url"):
        # A GitHub issue backs the item: let the merge close it.
        body += f"\n\nCloses {state['item_url']}"
    if state.get("pr_url"):
        state["pr_url"] = _https_url(state["pr_url"])
    else:
        git("push", "-u", "origin", state["branch"])
        listed = _run_checked([
            "gh", "pr", "list", "--state", "open", "--head", state["branch"],
            "--json", "url,state", "--limit", "1",
        ])
        try:
            existing = json.loads(listed)
        except ValueError as error:
            raise RuntimeError("gh pr list returned malformed JSON") from error
        if not isinstance(existing, list) or len(existing) > 1 or \
                any(not isinstance(item, dict) for item in existing):
            raise RuntimeError("gh pr list returned an invalid or ambiguous result")
        if existing and existing[0].get("state") not in ("OPEN", "CLOSED", "MERGED"):
            raise RuntimeError("gh pr list returned an invalid pull-request state")
        if existing and existing[0]["state"] == "OPEN":
            state["pr_url"] = _https_url(existing[0].get("url"))
        else:
            output = _run_checked([
                "gh", "pr", "create", "--base", config.BASE_BRANCH, "--head", state["branch"],
                "--title", _pr_title(state), "--body", body,
            ])
            state["pr_url"] = _https_url(output)
    state["pr_summary"] = body
    log.info("PR opened: %s", state["pr_url"])
    trail(state, f"PR opened: {state['pr_url']}", body)
    try:
        # Best-effort write-back (GitHub: move the item to review, link the PR on the
        # issue). The PR exists already; a backlog hiccup must not stall the flow.
        task_source.note_pr(state["item"], state.get("item_id"), state["pr_url"])
    except Exception:  # noqa: BLE001
        log.exception("could not link the PR on the backlog item")
    if not state.get("has_code_review"):
        log.info("no Code Review workflow detected for this task; finalizing without a review wait")
        finalize_pr(state)
        return
    # Don't notify the user yet: let the OpenCodeReview action run and address its
    # comments first (do_open_pr -> WAIT_REVIEW -> [ADDRESS_REVIEW -> WAIT_REVIEW]* -> WAIT_MERGE).
    state["review_round"] = 0
    state["review_run_link"] = None            # link of the last Code Review run we processed
    state["review_comment_watermark"] = ""     # only comments created after this are "new"
    _enter_review_wait(state)


# ---------------------------------------------------------------- automated review

def _pr_owner_number(pr_url: str) -> tuple[str, str]:
    """Parse 'https://github.com/OWNER/REPO/pull/N' into ('OWNER/REPO', 'N')."""
    m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url)
    if not m:
        raise ValueError(f"cannot parse owner/number from PR url: {pr_url!r}")
    return m.group(1), m.group(2)


def code_review_check(pr_url: str) -> dict | None:
    """The 'Code Review' workflow check for the PR's head commit, or None if not present yet.

    Returns the gh-pr-checks record (has 'bucket': pass|fail|pending|skipping|cancel,
    and 'link' identifying the specific run). gh exits non-zero while checks are pending
    or failing but still prints JSON, so we parse stdout rather than trust the exit code.
    A genuine gh failure (auth, network) also returns None but is logged at warning, so it
    surfaces promptly instead of masquerading as "not started" and stalling the poll loop
    until the review timeout.
    """
    try:
        proc = subprocess.run(
            ["gh", "pr", "checks", pr_url, "--json", "name,bucket,workflow,link"],
            cwd=config.REPO_PATH, capture_output=True, text=True,
            timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log.warning("gh pr checks timed out after %ss", config.SUBPROCESS_TIMEOUT_SECONDS)
        return None
    try:
        checks = json.loads(proc.stdout) if proc.stdout.strip() else []
    except json.JSONDecodeError:
        checks = None
    for c in checks or []:
        if c.get("workflow") == "Code Review" or c.get("name") == "code-review":
            return c
    if checks:
        # Real check data, but the Code Review run just hasn't registered yet.
        log.debug("gh pr checks: Code Review not among %d reported check(s) yet", len(checks))
    else:
        # No usable data. Empty output with a pending / "no checks reported" signal is the
        # normal pre-run state; unparseable output or an unexpected exit is a real tooling
        # failure that must not hide until REVIEW_WAIT_TIMEOUT_SECONDS elapses.
        stderr = proc.stderr.strip()
        benign = checks == [] and (proc.returncode in (0, 8) or "no checks reported" in stderr.lower())
        if benign:
            log.debug("gh pr checks: no checks reported yet (rc=%d)", proc.returncode)
        else:
            log.warning("gh pr checks failed (rc=%d): %s", proc.returncode, stderr[-300:] or "(no stderr)")
    return None


def _bot_comments(endpoint: str) -> list[dict]:
    """github-actions[bot] comments from a PR comments endpoint ([] on any failure)."""
    try:
        proc = subprocess.run(
            ["gh", "api", f"{endpoint}?per_page=100"],
            cwd=config.REPO_PATH, capture_output=True, text=True,
            timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log.warning("gh api %s timed out after %ss", endpoint, config.SUBPROCESS_TIMEOUT_SECONDS)
        return []
    if proc.returncode != 0:
        log.warning("gh api %s failed: %s", endpoint, proc.stderr[-300:])
        return []
    try:
        items = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return [c for c in items if c.get("user", {}).get("login") == "github-actions[bot]"]


def review_summary(state: dict) -> str:
    """The most recent OCR sticky-summary issue comment body, for extra context ('' if none)."""
    owner_repo, number = _pr_owner_number(state["pr_url"])
    summaries = _bot_comments(f"repos/{owner_repo}/issues/{number}/comments")
    if not summaries:
        return ""
    return max(summaries, key=lambda c: c.get("updated_at", "")).get("body", "")


def _enter_review_wait(state: dict, expect_new_run: bool = True) -> None:
    state["review_since"] = time.time()  # per-run wait clock (survives restarts via state.json)
    # True when a push should trigger a fresh Code Review run: the poll must then wait
    # for a NEW run link and never conclude from the already-processed run's state.
    state["await_new_run"] = expect_new_run
    state["state"] = "WAIT_REVIEW"


def _render_review_threads(state: dict, key: str = "review_threads") -> str:
    rendered = format_unresolved_threads(state.get(key, []), ids=True)
    summary = review_summary(state)
    if summary:
        rendered = "Reviewer summary (context):\n" + summary + "\n\n" + rendered
    return rendered


def finalize_pr(state: dict, note: str = "") -> None:
    """Record evidence and email the (now review-clean) PR, then wait for the user."""
    evidence_files = evidence.record_evidence(state.get("e2e_specs", []), state.get("e2e_kind"))
    log.info("recorded %d evidence file(s) to attach", len(evidence_files))
    evidence_files, video_url = _offload_evidence_video(state, evidence_files)
    body = f"Task: {state['item']}\nPR: {state['pr_url']}\n\n{state.get('pr_summary', '')}\n\n"
    if note:
        body += note + "\n\n"
    if video_url:
        # In the body (not a separate note) so email() mirrors it to the activity
        # trail: the issue comment / doc thread gets the same link.
        body += f"Evidence: a Playwright video demonstrating the feature.\nVideo: {video_url}\n"
    elif evidence_files:
        attachment_desc = ("a Newman run report (html)" if state.get("e2e_kind") == "newman"
                            else "a Playwright video (mp4)")
        body += f"Attached: {attachment_desc} demonstrating the feature.\n"
    elif state.get("has_e2e_harness"):
        body += ("Note: no e2e evidence could be captured for this PR (the spec/collection may "
                 "have skipped itself when re-run bare, or none matched — see codebot logs).\n")
    # Surface unresolved threads early — inline comments can land after the review run
    # finishes, and the merge gate re-checks before merging.
    threads = unresolved_review_threads(state["pr_url"])
    if threads is None:
        body += ("Note: I could not check the PR's review threads just now; "
                 "I will re-check before any merge.\n\n")
    elif threads:
        human = [t for t in threads if not _is_ocr_thread(t)]
        ocr = [t for t in threads if _is_ocr_thread(t)]
        if human:
            body += (f"Heads up: the PR has {len(human)} unresolved review comment(s) "
                     "from human reviewers; I'll address them while waiting, and I will "
                     "not merge until they are resolved (or you say 'merge anyway'):\n\n"
                     f"{format_unresolved_threads(human)}\n\n")
        if ocr:
            body += (f"Note: {len(ocr)} automated (OCR) review comment(s) are still "
                     "unresolved; I'll address them automatically — fixing or resolving "
                     "with an explanation — while waiting for your reply.\n\n")
    # A conflict resolution rewrote the PR after the user was invited to reply to it:
    # replies written against the OLD content (worst case a pending 'merge') must not
    # be executed against the new one. Set them aside and say so.
    if state.pop("stale_replies", None) and state.get("thread_id"):
        try:
            drained = gmail_client.drain_thread(state["thread_id"])
        except Exception:  # noqa: BLE001 — a gmail hiccup must not block the finalize
            log.exception("could not check the thread for stale replies")
            drained = 0
        if drained:
            body += (f"Note: the PR changed while I resolved merge conflicts with "
                     f"{config.BASE_BRANCH}, so {drained} earlier repl(y/ies) on this thread "
                     "were set aside — please re-send your instruction against the updated "
                     "PR.\n\n")
    body += "Reply with change requests, or tell me to merge."
    email(state, "PR ready for review", body, evidence_files)
    # pr_summary is kept (until the task ends) so a later re-finalize — e.g. after a
    # conflict resolution — doesn't email an empty summary.
    for key in ("review_since", "review_round", "review_run_link", "review_threads",
                "await_new_run"):
        state.pop(key, None)
    state["state"] = "WAIT_MERGE"


def handle_review_wait(state: dict) -> None:
    """Poll the Code Review action; when a new run finishes, work the PR's UNRESOLVED
    OCR threads (fix or resolve-with-comment) until none remain, then finalize.

    Unresolved threads — not "comments newer than a watermark" — are the work queue:
    a thread the worker skipped, or one posted after a run was processed, stays in the
    queue instead of silently accumulating until merge time."""
    check = code_review_check(state["pr_url"])
    bucket = check.get("bucket") if check else None
    same_run = check is not None and check.get("link") == state.get("review_run_link")
    if check is None or bucket == "pending" or same_run:
        if same_run and bucket and bucket != "pending" and not state.get("await_new_run"):
            # No new run is coming (a resolution-only round pushes nothing) and the
            # processed run is finished. If every OCR thread is resolved, the PR is
            # clean — finalize now instead of waiting out the review timeout. When a
            # push IS expected (await_new_run), never conclude from the old run: the
            # fixes still need their re-review.
            threads = unresolved_review_threads(state["pr_url"])
            if threads is not None and not [t for t in threads if _is_ocr_thread(t)]:
                log.info("no unresolved OCR threads on the processed run; PR is clean")
                finalize_pr(state)
                return
        # Not started, still running, or the previous run's result — keep waiting, but
        # don't block the PR forever if the action is stuck or never triggered.
        if time.time() - state.get("review_since", time.time()) > config.REVIEW_WAIT_TIMEOUT_SECONDS:
            log.warning("Code Review did not complete within %ss; notifying user without it",
                        config.REVIEW_WAIT_TIMEOUT_SECONDS)
            finalize_pr(state, note="Note: the automated code review did not finish in time, "
                                    "so I'm sending this without waiting for it.")
        else:
            log.debug("waiting for Code Review (bucket=%s, same_run=%s)", bucket, same_run)
        return
    # A new Code Review run finished (pass/fail/skip/cancel). Read what is unresolved.
    threads = unresolved_review_threads(state["pr_url"])
    if threads is None:
        # Transient query failure: don't record the run as processed, so the next tick
        # re-reads it (the review timeout still bounds the wait).
        log.warning("could not fetch review threads; retrying next tick")
        return
    state["review_run_link"] = check.get("link")
    ocr = [t for t in threads if _is_ocr_thread(t)]
    if not ocr:
        log.info("no unresolved OCR threads; PR is clean")
        finalize_pr(state)
        return
    if state.get("review_round", 0) >= config.REVIEW_MAX_ROUNDS:
        log.warning("review round limit (%d) reached with %d open thread(s); finalizing",
                    config.REVIEW_MAX_ROUNDS, len(ocr))
        finalize_pr(state, note=(
            f"Note: the automated reviewer still has {len(ocr)} unresolved thread(s) after "
            f"{config.REVIEW_MAX_ROUNDS} rounds of fixes. I've left them on the PR for you."))
        return
    state["review_threads"] = ocr
    state["state"] = "ADDRESS_REVIEW"
    log.info("%d unresolved OCR thread(s); addressing them", len(ocr))


def do_address_review(state: dict) -> None:
    threads = state.get("review_threads", [])
    state["review_round"] = state.get("review_round", 0) + 1
    log.info("addressing %d review thread(s), round %d", len(threads), state["review_round"])
    trail(state, f"Addressing {len(threads)} automated review thread(s), round "
                 f"{state['review_round']}")
    head_before = git("rev-parse", state["branch"])
    result = agent_runner.resume(
        state["session_id"],
        prompts.render(prompts.ADDRESS_REVIEW, threads=_render_review_threads(state),
                       branch=state["branch"]))
    if handle_result(state, result, "ADDRESS_REVIEW"):
        return
    _finish_address_review(state, result, head_before)


def _finish_address_review(state: dict, result, head_before: str | None) -> None:
    """Success tail of ADDRESS_REVIEW: new commits are pushed (via PUSHING) and re-reviewed;
    a resolution-only round resolves the threads right away and re-checks the PR."""
    if _scrub_evidence_from_repo(state, "ADDRESS_REVIEW") is None:
        return
    committed = head_before is None or git("rev-parse", state["branch"]) != head_before
    if committed:
        # The RESOLVE lines are acted on after the push lands (see do_push), so the
        # thread replies never describe a fix that isn't on GitHub yet.
        _queue_push(state, "review", result.output)
        return
    # Resolution-only round: no new review run is coming. Re-check and either finish
    # or hand the leftovers straight back (the round cap bounds this loop).
    _resolve_review_threads(state, result.output)
    state.pop("review_threads", None)
    remaining = unresolved_review_threads(state["pr_url"])
    if remaining is None:
        # Could not verify — never conclude "clean" from a failed query. The review
        # wait's clean-check retries the query each tick (bounded by its timeout).
        _enter_review_wait(state, expect_new_run=False)
        return
    ocr = [t for t in remaining if _is_ocr_thread(t)]
    if ocr:
        log.info("%d OCR thread(s) still unresolved after the round; re-addressing", len(ocr))
        state["review_threads"] = ocr
        state["state"] = "ADDRESS_REVIEW"
        return
    finalize_pr(state)


# ---------------------------------------------------------------- base-branch conflicts

def _pr_merge_state(pr_url: str) -> tuple[str | None, str | None]:
    """(state, mergeable) of the PR — e.g. ("OPEN", "CONFLICTING") — or (None, None)
    when the query fails. Callers treat that as "unknown", never as "clean"."""
    try:
        proc = subprocess.run(["gh", "pr", "view", pr_url, "--json", "state,mergeable"],
                              cwd=config.REPO_PATH, capture_output=True, text=True,
                              timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log.warning("gh pr view timed out checking mergeability")
        return None, None
    if proc.returncode != 0:
        log.warning("gh pr view failed checking mergeability: %s", proc.stderr[-300:])
        return None, None
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError:
        log.warning("gh pr view returned non-JSON checking mergeability: %s", proc.stdout[:200])
        return None, None
    return info.get("state"), info.get("mergeable")


def _enter_conflict_resolution(state: dict) -> bool:
    """Route the task into RESOLVE_CONFLICTS, bounded by CONFLICT_MAX_ROUNDS: the base
    branch can keep moving while other PRs merge, so a resolution that never converges
    must escalate to the user instead of looping forever. Returns True when the
    resolution state was actually entered (False = escalated to WAIT_STUCK instead)."""
    rounds = state.get("conflict_rounds", 0) + 1
    state["conflict_rounds"] = rounds
    if rounds > config.CONFLICT_MAX_ROUNDS:
        _enter_stuck(state, state["state"],
                     f"The PR still conflicts with {config.BASE_BRANCH} after "
                     f"{config.CONFLICT_MAX_ROUNDS} resolution attempt(s).\nPR: "
                     f"{state.get('pr_url', '?')}\n\n"
                     f"Please resolve the conflicts on the branch yourself (merge "
                     f"{config.BASE_BRANCH} in and push), then reply 'retry'.")
        return False
    log.warning("PR %s conflicts with %s (attempt %d/%d); entering RESOLVE_CONFLICTS",
                state.get("pr_url"), config.BASE_BRANCH, rounds, config.CONFLICT_MAX_ROUNDS)
    # Where a no-op resolution returns to. From WAIT_MERGE the user was already invited
    # to reply on the current PR content; a reply written before the resolution rewrote
    # the PR must not be acted on later — finalize_pr sets those aside (stale_replies).
    state["conflict_return"] = state["state"]
    if state["state"] == "WAIT_MERGE":
        state["stale_replies"] = True
    state["state"] = "RESOLVE_CONFLICTS"
    return True


def check_pr_conflicts(state: dict) -> bool:
    """While waiting with an open PR, watch for the base branch having moved under it
    (another PR merged). A CONFLICTING PR is routed to RESOLVE_CONFLICTS; returns True
    when the state changed. Query failures (and GitHub's transient "UNKNOWN" while it
    recomputes mergeability) change nothing — the next tick re-checks."""
    if not state.get("pr_url"):
        return False
    pr_state, mergeable = _pr_merge_state(state["pr_url"])
    if pr_state != "OPEN":
        return False  # merged/closed/unknown: nothing to resolve here
    if mergeable != "CONFLICTING":
        if mergeable == "MERGEABLE":
            state.pop("conflict_rounds", None)  # healthy again; reset the attempt cap
        return False
    _enter_conflict_resolution(state)
    return True


def do_resolve_conflicts(state: dict) -> None:
    """Merge the base branch into the task branch in the working session. A conflict
    with genuinely different reasonable resolutions comes back as a NEED_USER_INPUT
    question and is emailed like any other; a clean resolution is pushed and goes
    through the automated review again before it can merge."""
    # Persisted (not a local) so the WAIT_REPLY question detour can also tell whether
    # the answer-informed session ended up committing.
    state["conflict_head"] = git("rev-parse", state["branch"])
    result = agent_runner.resume(
        state["session_id"],
        prompts.render(prompts.RESOLVE_CONFLICTS, branch=state["branch"],
                       base_branch=config.BASE_BRANCH))
    if handle_result(state, result, "RESOLVE_CONFLICTS"):
        return
    _leave_conflict_resolution(state)


def _leave_conflict_resolution(state: dict) -> None:
    """Exit RESOLVE_CONFLICTS based on whether the session committed. A commit is pushed
    (PUSHING) and goes through the automated review again (never merge unreviewed
    commits). No commit returns to the state the conflict preempted — NOT to WAIT_REVIEW,
    which after a finalize (review_run_link already popped) would misread the old
    finished run as new and re-finalize with a duplicate email; the per-tick conflict
    check re-detects a leftover conflict from either wait state, bounded by the cap."""
    committed = git("rev-parse", state["branch"]) != state.get("conflict_head")
    state.pop("conflict_head", None)
    if committed:
        log.info("conflict resolution produced new commits; pushing them for re-review")
        trail(state, "Merge conflicts resolved; pushing for re-review")
        state.pop("conflict_return", None)
        _queue_push(state, "conflicts")
        return
    origin = state.pop("conflict_return", "WAIT_MERGE")
    log.warning("conflict-resolution session committed nothing; returning to %s", origin)
    if origin == "WAIT_REVIEW":
        _enter_review_wait(state, expect_new_run=False)
    else:
        state.pop("stale_replies", None)  # the PR did not change; replies are not stale
        state["state"] = origin


# ---------------------------------------------------------------- pre-merge thread resolution

def unresolved_review_threads(pr_url: str) -> list[dict] | None:
    """All unresolved review threads on the PR — ANY author, not just the OCR bot — via
    GraphQL (REST doesn't expose thread resolution). Returns None when the query fails,
    which callers must treat as "could not verify", never as "no threads": this gates an
    irreversible merge, so it fails closed."""
    owner_repo, number = _pr_owner_number(pr_url)
    owner, repo = owner_repo.split("/", 1)
    query = """
    query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          reviewThreads(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id isResolved isOutdated path line
              comments(first: 1) { nodes { author { login } body databaseId } } } } } } }"""
    threads: list[dict] = []
    cursor = None
    while True:
        # -f passes raw strings; only $number (an Int in the query) uses -F's type
        # coercion. An all-digit cursor or owner under -F would coerce to Int and make
        # the GraphQL call fail its String! variable types.
        cmd = ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"owner={owner}",
               "-f", f"repo={repo}", "-F", f"number={number}"]
        if cursor:
            cmd += ["-f", f"cursor={cursor}"]
        try:
            proc = subprocess.run(cmd, cwd=config.REPO_PATH, capture_output=True, text=True,
                                  timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            log.warning("gh api graphql (review threads) timed out")
            return None
        if proc.returncode != 0:
            log.warning("gh api graphql (review threads) failed: %s", proc.stderr[-300:])
            return None
        try:
            conn = (json.loads(proc.stdout)["data"]["repository"]["pullRequest"]
                    ["reviewThreads"])
        except (json.JSONDecodeError, KeyError, TypeError) as err:
            log.warning("unexpected review-threads payload (%s): %s", err, proc.stdout[:300])
            return None
        for node in conn.get("nodes") or []:
            if node.get("isResolved"):
                continue
            first = ((node.get("comments") or {}).get("nodes") or [{}])[0]
            threads.append({
                "id": node.get("id"),
                "comment_id": first.get("databaseId"),
                "path": node.get("path"),
                "line": node.get("line"),
                "outdated": bool(node.get("isOutdated")),
                "author": (first.get("author") or {}).get("login", "?"),
                "body": first.get("body", ""),
            })
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    log.info("PR has %d unresolved review thread(s)", len(threads))
    return threads


def format_unresolved_threads(threads: list[dict], ids: bool = False) -> str:
    lines = []
    for i, t in enumerate(threads, 1):
        loc = f"{t['path']}:{t['line']}" if t.get("line") else (t.get("path") or "(general)")
        tag = " [outdated code]" if t.get("outdated") else ""
        head = f"[{i}] {loc} ({t.get('author', '?')}){tag}"
        if ids:
            head += f"\nthread_id: {t.get('id')}"
        body = (t.get("body") or "").strip()
        if len(body) > 400 and not ids:  # full text when the worker must act on it
            body = body[:400] + "…"
        lines.append(f"{head}\n{body}")
    return "\n\n".join(lines)


def _is_ocr_thread(thread: dict) -> bool:
    """True when the thread was opened by the OCR workflow's bot account (GraphQL says
    'github-actions', REST says 'github-actions[bot]' — accept both)."""
    author = (thread.get("author") or "").strip()
    return author.removesuffix("[bot]") == "github-actions"


def _resolve_review_threads(state: dict, output: str, key: str = "review_threads") -> int:
    """Act on the worker's `RESOLVE: <thread_id> <reason>` lines: post the reason as a
    reply on the thread and mark the thread resolved. Only thread ids the orchestrator
    itself fetched (state[key]) are honored — model output cannot resolve arbitrary
    threads. Failures are logged and skipped; an unresolved thread is caught again by
    the next round or the merge gate. Returns the number resolved."""
    known = {t["id"]: t for t in state.get(key, []) if t.get("id")}
    if not known:
        return 0
    owner_repo, number = _pr_owner_number(state["pr_url"])
    resolved = 0
    for line in output.splitlines():
        if not line.startswith("RESOLVE:"):
            continue
        thread_id, _, reason = line[len("RESOLVE:"):].strip().partition(" ")
        thread = known.get(thread_id)
        if thread is None:
            log.warning("ignoring RESOLVE for unknown thread %r", thread_id[:80])
            continue
        reason = reason.strip() or "Resolved by codebot."
        try:
            if thread.get("comment_id"):
                reply = subprocess.run(
                    ["gh", "api", f"repos/{owner_repo}/pulls/{number}/comments/"
                     f"{thread['comment_id']}/replies", "-f", f"body={reason}"],
                    cwd=config.REPO_PATH, capture_output=True, text=True,
                    timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
                if reply.returncode != 0:
                    log.warning("could not reply on thread %s: %s",
                                thread_id, reply.stderr[-300:])
            if resolve_review_thread(thread_id):
                resolved += 1
                log.info("resolved review thread %s (%s)", thread_id, reason[:100])
        except subprocess.TimeoutExpired:
            log.warning("resolving thread %s timed out", thread_id)
    log.info("resolved %d/%d review thread(s) from RESOLVE lines", resolved, len(known))
    return resolved


def resolve_review_thread(thread_id: str) -> bool:
    try:
        proc = subprocess.run(
            ["gh", "api", "graphql",
             "-f", "query=mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }",
             "-f", f"id={thread_id}"],
            cwd=config.REPO_PATH, capture_output=True, text=True,
            timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log.warning("gh api graphql (resolveReviewThread %s) timed out", thread_id)
        return False
    if proc.returncode != 0:
        log.warning("gh api graphql (resolveReviewThread %s) failed: %s", thread_id, proc.stderr[-300:])
        return False
    return True


def do_merge_reply(state: dict, reply: str) -> None:
    result = agent_runner.run(prompts.render(prompts.CLASSIFY_PR_REPLY, reply=reply),
                              contract=False)
    verdict = parse_json_reply(result.output)
    action = verdict.get("action")
    log.info("classified PR reply as action=%r force=%r", action, verdict.get("force"))
    if action not in ("merge", "changes", "abort", "complete"):
        # Merging is irreversible: never fall through to it on unexpected output.
        email(state, "clarification needed",
              f"I could not tell whether your reply asks for changes, an abort, a "
              f"merge, or to mark the task complete:\n\n{reply}\n\nPlease reply again "
              "with the change requests, 'abort', 'complete', or an explicit 'merge'.")
        return  # stay in WAIT_MERGE
    if action == "complete":
        _finish_task(state, "You asked me to mark this task complete without merging the PR "
                            f"myself.\nPR: {state.get('pr_url', '-')}", reset_repo=True)
        return
    if action == "abort":
        pr_url = state.get("pr_url", "-")
        _abort_and_reset(state, "Got it — I'm stopping this task and resetting to a clean "
                                f"slate.\n\nPR: {pr_url}")
        return
    if action == "changes":
        r = agent_runner.resume(
            state["session_id"],
            prompts.render(prompts.APPLY_PR_FEEDBACK, feedback=verdict.get("feedback", ""), branch=state["branch"]))
        if handle_result(state, r, "APPLY_PR_FEEDBACK"):
            return
        extra_attachments = _scrub_evidence_from_repo(state, "APPLY_PR_FEEDBACK")
        if extra_attachments is None:
            return
        attachments = _collect_attachments(r, state.get("e2e_specs", []), state.get("e2e_kind"))
        attachments += [a for a in extra_attachments if a.resolve() not in {p.resolve() for p in attachments}]
        _queue_push(state, "feedback", r.output, attachments)
        return
    # merge
    pr_state, mergeable = _pr_merge_state(state["pr_url"])
    log.info("PR state=%s mergeable=%s before merge", pr_state, mergeable)
    if pr_state is None:
        email(state, "merge blocked — could not check the PR",
              f"I did not merge: I couldn't query the PR's state just now.\nPR: "
              f"{state['pr_url']}\n\nReply 'merge' to retry.")
        return  # stay in WAIT_MERGE
    if pr_state != "MERGED":
        if mergeable == "CONFLICTING":
            # The base branch moved ahead and the branch no longer merges cleanly.
            # Resolve the conflicts in the working session; genuinely ambiguous
            # resolutions come back as an emailed question. The resolution push then
            # needs its re-review before the user's next 'merge'. The announcement is
            # sent only if resolution actually starts — past the attempt cap
            # _enter_conflict_resolution emails the (opposite) stuck instructions instead.
            log.warning("PR %s conflicts with %s; resolving before the merge",
                        state["pr_url"], config.BASE_BRANCH)
            if _enter_conflict_resolution(state):
                email(state, "merge conflict — resolving automatically",
                      f"`{config.BASE_BRANCH}` has changed and this PR now conflicts with "
                      f"it, so I can't merge it yet.\nPR: {state['pr_url']}\n\n"
                      "I'm resolving the conflicts now. If any conflict has genuinely "
                      "different reasonable resolutions I'll email you the alternatives; "
                      "otherwise the automated review re-runs on the resolved branch and "
                      "I'll email when it's clean — reply 'merge' then.")
            return
        # Review-thread gate: inline review threads may appear at any time, including
        # after the "PR ready" email (handle_merge_wait addresses them proactively, but
        # only up to its round cap). Never squash-merge over unresolved feedback unless
        # the user explicitly forces it. Fails CLOSED: a failed thread query blocks the
        # merge, never waves it through. The strict `is True` matters — classifier JSON
        # isn't schema-validated, and a string like "false" is truthy.
        if verdict.get("force") is not True:
            threads = unresolved_review_threads(state["pr_url"])
            if threads is None:
                email(state, "merge blocked — could not verify review comments",
                      f"I did not merge: I couldn't query the PR's review threads to check "
                      f"for unresolved comments.\nPR: {state['pr_url']}\n\n"
                      "Reply 'merge' to have me retry the check, or 'merge anyway' to merge "
                      "without it.")
                return  # stay in WAIT_MERGE
            if threads:
                log.warning("merge blocked: %d unresolved review thread(s)", len(threads))
                email(state, "merge blocked — unresolved review comments",
                      f"I did not merge: the PR has {len(threads)} unresolved review "
                      f"thread(s).\nPR: {state['pr_url']}\n\n"
                      f"{format_unresolved_threads(threads)}\n\n"
                      "Options: reply with change requests and I'll address them; resolve "
                      "the threads on GitHub and reply 'merge' again; or reply 'merge "
                      "anyway' to merge despite them.")
                state["pr_thread_notified"] = True  # don't re-address them every tick
                return  # stay in WAIT_MERGE
        log.info("merging PR %s (squash)", state["pr_url"])
        merge = subprocess.run(["gh", "pr", "merge", state["pr_url"], "--squash"],
                               cwd=config.REPO_PATH, capture_output=True, text=True, timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
        if merge.returncode != 0:
            # A late-breaking conflict or other GitHub rejection (e.g. branch behind the
            # base branch). Don't crash into the retry loop — surface it and wait for the
            # user to fix it.
            log.warning("gh pr merge failed (%d): %s", merge.returncode, merge.stderr.strip())
            email(state, "merge failed — needs your help",
                  f"I couldn't merge the PR; GitHub reported:\n\n{merge.stderr.strip()}\n\n"
                  f"PR: {state['pr_url']}\n\nThis usually means {config.BASE_BRANCH} moved ahead "
                  "or there are conflicts. If it's a merge conflict I'll detect it and start "
                  "resolving automatically on my next check; otherwise please resolve it on "
                  "the branch and reply 'merge' to retry.")
            return  # stay in WAIT_MERGE
        trail(state, f"PR merged: {state['pr_url']}")
    _finish_task(state, "PR merged.", reset_repo=False)


def _finish_address_pr_threads(state: dict) -> None:
    """After the fixes are pushed: reply on + resolve the threads the worker declared
    handled (RESOLVE lines, kept in the push context). Threads without a RESOLVE line
    stay open and are picked up again next tick, bounded by PR_THREAD_MAX_ROUNDS."""
    output = (state.get("push_context") or {}).get("output", "")
    resolved = _resolve_review_threads(state, output, key="pr_threads")
    threads = state.pop("pr_threads", [])
    if resolved < len(threads):
        log.warning("%d/%d review thread(s) still unresolved after the round",
                    len(threads) - resolved, len(threads))
    state["state"] = "WAIT_MERGE"


def do_address_pr_threads(state: dict) -> None:
    threads = state.get("pr_threads", [])
    state["pr_thread_round"] = state.get("pr_thread_round", 0) + 1
    log.info("addressing %d unresolved review thread(s), round %d", len(threads), state["pr_thread_round"])
    result = agent_runner.resume(
        state["session_id"],
        prompts.render(prompts.ADDRESS_PR_THREADS,
                       threads=_render_review_threads(state, key="pr_threads"),
                       branch=state["branch"]))
    if handle_result(state, result, "ADDRESS_PR_THREADS"):
        return
    if _scrub_evidence_from_repo(state, "ADDRESS_PR_THREADS") is None:
        return
    _queue_push(state, "threads", result.output)


def _queue_push(state: dict, continuation: str, output: str = "",
                attachments: list[Path] | None = None) -> None:
    state["push_context"] = {
        "continuation": continuation,
        "output": str(output),
        "attachments": [str(path) for path in attachments or []],
    }
    state["state"] = "PUSHING"
    save_state(state)


def do_push(state: dict) -> None:
    context = state.get("push_context")
    if not isinstance(context, dict):
        raise RuntimeError("PUSHING state is missing push_context")
    continuation = context.get("continuation")
    if continuation not in ("review", "feedback", "threads", "conflicts"):
        raise RuntimeError(f"invalid push continuation: {continuation!r}")

    git("push", "origin", state["branch"])
    if continuation == "review":
        # The fix is on GitHub now: reply on + resolve the threads the worker declared
        # handled, then wait for the re-review the push triggers.
        _resolve_review_threads(state, context.get("output", ""))
        state.pop("review_threads", None)
        state.pop("review_comments", None)
        _enter_review_wait(state)
    elif continuation == "conflicts":
        _enter_review_wait(state)  # the resolved branch needs its re-review
    elif continuation == "feedback":
        attachments = [Path(path) for path in context.get("attachments", [])]
        attachments, video_url = _offload_evidence_video(state, attachments)
        body = f"Applied your feedback.\nPR: {state['pr_url']}\n\n{context.get('output', '')}"
        if video_url:
            body += f"\n\nVideo: {video_url}"
        email(state, "PR updated", body, attachments)
        state["state"] = "WAIT_MERGE"
    else:
        _finish_address_pr_threads(state)
    state.pop("push_context", None)


# ---------------------------------------------------------------- silence check-ins

# A task thread that stays quiet for longer than the current back-off interval gets a
# short check-in, so the user can tell a long-running step from a wedged bot. The clock
# lives in state.json (survives restarts) and restarts on any REAL email in either
# direction on the task thread: every email() call and every consumed reply. Check-ins
# themselves bypass email() so they neither restart the clock nor displace last_email,
# which STATUS and the check-ins quote as "what I'm waiting on". They are sent from the
# tick loop, so one can lag while a single long agent call runs (bounded by
# CODEBOT_AGENT_TIMEOUT); it goes out as soon as that call returns.
PING_KEYS = ("last_contact", "ping_count", "last_ping_at")
# Waits whose next move is the user's: the check-in spells out what is expected in full.
USER_SIDE_WAITS = {"WAIT_APPROVAL", "WAIT_MERGE", "WAIT_REPLY", "WAIT_STUCK", "WAIT_CLEAN"}

_PHASE_ACTIVITY = {
    "EXPLORING": "exploring the codebase to understand the task before writing a proposal",
    "PROPOSING": "writing the OpenSpec proposal (design, specs, tasks) for your review",
    "IMPLEMENTING": "implementing the approved proposal on branch {branch}",
    "VERIFYING": "running the verification gate (tests and checks) on the implementation",
    "INTERNAL_REVIEW": "running an internal code review of the implementation and fixing "
                       "its findings",
    "E2E": "running the e2e test harness against the implementation",
    "ARCHIVING": "archiving the OpenSpec change on the task branch before opening the PR",
    "OPEN_PR": "pushing branch {branch} and opening the pull request",
    "ADDRESS_REVIEW": "working through {n_review} unresolved thread(s) from the automated "
                      "reviewer on the PR {pr_url}",
    "ADDRESS_PR_THREADS": "working through {n_pr} unresolved review thread(s) on the PR "
                          "{pr_url} before it can merge",
    "RESOLVE_CONFLICTS": "resolving merge conflicts between the task branch and {base} "
                         "on the PR {pr_url}",
    "PUSHING": "pushing the latest commits to the PR branch {branch}",
}


def _fmt_dur(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes or not parts:
        parts.append(f"{minutes} min")
    return " ".join(parts)


def _note_contact(state: dict) -> None:
    """A real email was sent or received on the task thread: restart the silence clock."""
    state["last_contact"] = time.time()
    state.pop("ping_count", None)
    state.pop("last_ping_at", None)


def _ping_interval(count: int) -> int:
    """Silence tolerated before check-in number `count + 1` (the last interval repeats)."""
    schedule = config.PING_SCHEDULE_SECONDS
    return schedule[min(count, len(schedule) - 1)]


def _ping_due(state: dict, now: float) -> bool:
    if (not config.PING_SCHEDULE_SECONDS or state.get("state") == "IDLE"
            or not state.get("thread_id")):
        return False
    anchor = state.get("last_ping_at")
    if anchor is None:
        anchor = state.get("last_contact")
    if anchor is None:
        # A task that predates the check-ins (state.json from an older build): start the
        # clock now rather than pinging on the spot.
        state["last_contact"] = now
        return False
    return now - anchor >= _ping_interval(state.get("ping_count", 0))


def _expected_from_user(state: dict) -> str:
    """What the current wait needs from the user, spelled out in full: a check-in must
    stand on its own, never "see my earlier email"."""
    st = state["state"]
    if st == "WAIT_APPROVAL":
        return ("your decision on the proposal I sent for this task. Reply with an explicit "
                "approval to start implementing, with the changes you want made to the "
                "proposal, 'complete' to mark the task done without further work, or "
                "'abort' to drop it.")
    if st == "WAIT_MERGE":
        text = (f"your decision on the pull request: {state.get('pr_url', '?')}\n"
                "Reply 'merge' to merge it, with the changes you want made to the PR, "
                "'complete' to mark the task done without merging, or 'abort' to drop it.")
        if state.get("pr_thread_notified"):
            text += (f"\nThe PR still has unresolved review threads I could not clear after "
                     f"{config.PR_THREAD_MAX_ROUNDS} round(s): resolve them on GitHub, or "
                     "reply 'merge anyway' to merge regardless.")
        return text
    if st == "WAIT_REPLY":
        question = state.get("pending_question") or "(question not recorded; see my last email below)"
        return (f"your answer to the question I asked during {state.get('return_state', '?')}:"
                f"\n\n{question}")
    if st == "WAIT_STUCK":
        text = (f"help with the step I'm stuck on ({state.get('stuck_return', '?')}). Reply "
                "'retry' to try that step again, 'abort' to reset to a clean slate, "
                "'complete' to mark the task done as-is, or reply with instructions and "
                "I'll apply them and continue.")
        if state.get("stuck_error"):
            text += f"\nThe problem was:\n\n{state['stuck_error']}"
        return text
    if st == "WAIT_CLEAN":
        return (f"a clean working tree in {config.REPO_PATH}: it has uncommitted changes to "
                "tracked files and I won't start a task on top of them. Commit, stash or "
                "discard them, then reply to this thread (any text) and I'll retry.")
    return "your reply to my last email (quoted below)."


def _review_wait_status(state: dict, now: float) -> str:
    pr_url = state.get("pr_url", "?")
    lines = [f"I'm waiting for the 'Code Review' GitHub Action to finish on the PR: {pr_url}"]
    since = state.get("review_since")
    if since:
        remaining = config.REVIEW_WAIT_TIMEOUT_SECONDS - (now - since)
        line = f"Waiting since {_fmt_ts(since)} ({_fmt_dur(now - since)} so far)"
        if remaining > 0:
            line += (f"; if it hasn't finished in another {_fmt_dur(remaining)} I'll email "
                     "you the PR without it.")
        else:
            line += "; that is past my wait limit, so I'm about to email you the PR without it."
        lines.append(line)
    try:
        check = code_review_check(pr_url)
    except Exception:  # noqa: BLE001 — a gh hiccup must not sink the check-in
        log.exception("could not query the Code Review check for the check-in")
        check = None
    if check is None:
        lines.append("GitHub does not report a Code Review run for the PR's latest commit yet.")
    elif check.get("link") and check.get("link") == state.get("review_run_link"):
        lines.append(f"GitHub still reports the run I already processed ({check.get('bucket')}); "
                     "I'm waiting for the new run my latest push triggers.")
    else:
        lines.append(f"GitHub reports the run as: {check.get('bucket', '?')}"
                     + (f" ({check['link']})" if check.get("link") else ""))
    if state.get("review_round"):
        lines.append(f"Automated review round {state['review_round']} of at most "
                     f"{config.REVIEW_MAX_ROUNDS}.")
    lines.append("When it finishes I'll fix or answer any unresolved review threads, then "
                 "email you the PR.")
    return "\n".join(lines)


def _bot_side_activity(state: dict, now: float) -> str:
    st = state["state"]
    if st == "WAIT_REVIEW":
        return _review_wait_status(state, now)
    what = _PHASE_ACTIVITY.get(st, f"working through the {st} step").format(
        branch=state.get("branch", "?"), base=config.BASE_BRANCH,
        pr_url=state.get("pr_url", "?"), n_review=len(state.get("review_threads", [])),
        n_pr=len(state.get("pr_threads", [])))
    lines = [f"I'm {what}."]
    started = state.get("last_transition")
    if started:
        lines.append(f"This step started at {_fmt_ts(started)} ({_fmt_dur(now - started)} ago).")
    return "\n".join(lines)


def _ping_body(state: dict, now: float, count: int) -> str:
    st = state["state"]
    last_contact = state.get("last_contact")
    if last_contact is None:
        last_contact = now
    lines = [f"Task: {state.get('item', '-')}", f"State: {st}",
             f"This thread has been quiet for {_fmt_dur(now - last_contact)} (last real email "
             f"sent or received: {_fmt_ts(last_contact)}), so here is where things stand.", ""]
    if st in USER_SIDE_WAITS:
        lines.append("The ball is in your court: I'm waiting for " + _expected_from_user(state))
        lines += ["", "Nothing has changed on my side since my last email."]
        last = state.get("last_email")
        if last:
            lines += ["", f"--- For reference, my last email ({_fmt_ts(last['sent_at'])}) ---",
                      f"Subject: {last['subject']}", "", last["body"]]
    else:
        lines.append("The ball is in my court; nothing is needed from you right now.")
        lines.append(_bot_side_activity(state, now))
        failed = state.get("failures", {}).get(st, 0)
        if failed:
            lines.append(f"Heads up: the last {failed} attempt(s) at this step failed and I'm "
                         f"retrying; after {config.MAX_STATE_FAILURES} in a row I'll stop and "
                         "ask for your help.")
        lines.append("I'll email you as soon as I need something from you or have a result "
                     "to show.")
    lines += ["", f"(Check-in {count}. Unless something happens on this thread, the next one "
                  f"comes in about {_fmt_dur(_ping_interval(count))}. Reply STATUS for a full "
                  "snapshot, HOLD to park this task, or ABORT to drop it.)"]
    return "\n".join(lines)


def _maybe_ping(state: dict) -> None:
    """Every tick: send a silence check-in when one is due. Never raises — a check-in is a
    courtesy and must not burn the current state's failure budget."""
    try:
        now = time.time()
        if not _ping_due(state, now):
            return
        count = state.get("ping_count", 0) + 1
        body = _ping_body(state, now, count)
        gmail_client.send(subject(state, "check-in"), body, state["thread_id"])
        state["ping_count"] = count
        state["last_ping_at"] = now
        log.info("sent silence check-in #%d in %s (thread quiet for %s)", count, state["state"],
                 _fmt_dur(now - state.get("last_contact", now)))
    except Exception:  # noqa: BLE001
        log.exception("could not send the silence check-in; will retry next tick")


# ---------------------------------------------------------------- loop

PHASES = {
    "IDLE": do_pick,
    "EXPLORING": do_explore,
    "PROPOSING": do_propose,
    "IMPLEMENTING": do_implement,
    "VERIFYING": do_verify,
    "INTERNAL_REVIEW": do_internal_review,
    "E2E": do_e2e,
    "ARCHIVING": do_archive,
    "OPEN_PR": do_open_pr,
    "ADDRESS_REVIEW": do_address_review,
    "ADDRESS_PR_THREADS": do_address_pr_threads,
    "RESOLVE_CONFLICTS": do_resolve_conflicts,
    "PUSHING": do_push,
}

# WAIT_REVIEW polls the Code Review action rather than the inbox, but shares the
# post-tick sleep, so it lives in WAITS and is dispatched ahead of the inbox waits.
# WAIT_MERGE does too: it also checks the PR for unresolved review threads before
# falling through to the inbox check (see handle_merge_wait).
WAITS = {"WAIT_APPROVAL", "WAIT_MERGE", "WAIT_REPLY", "WAIT_CLEAN", "WAIT_REVIEW", "WAIT_STUCK"}


def handle_wait(state: dict) -> None:
    polled = gmail_client.poll_reply(state["thread_id"]) if state.get("thread_id") else None
    if polled is None:
        log.debug("%s: no reply yet on thread %s", state["state"], state.get("thread_id"))
        return
    msg_id, reply = polled
    target = gmail_client.foreign_command(reply)
    if target:
        # A command addressed to ANOTHER instance, replied on our thread. That
        # instance picks it up mailbox-wide; classifying it here as the user's answer
        # could abort or complete OUR task on a command that was never for us.
        log.info("setting aside command for instance %r replied on our thread", target)
        gmail_client.mark_processed(msg_id)
        return
    log.info("reply received in %s: %r", state["state"], reply[:200])
    _note_contact(state)
    _handle_reply(state, reply)
    # Consume the reply only now that handling finished without raising. If it threw
    # (e.g. a transient claude failure), the message stays unprocessed so the next tick
    # re-reads and re-handles it instead of silently dropping the user's reply.
    gmail_client.mark_processed(msg_id)


def handle_merge_wait(state: dict) -> None:
    """Every WAIT_MERGE poll: check the open PR for unresolved review threads (e.g. a
    human reviewer's) and address them, so live feedback gets fixed before the user
    even says 'merge'. Falls through to the normal inbox check either way."""
    threads = unresolved_review_threads(state["pr_url"])
    if threads is None:
        log.warning("could not fetch review threads; checking the inbox only this tick")
    elif not threads:
        state.pop("pr_thread_round", None)
        state.pop("pr_thread_notified", None)
    elif state.get("pr_thread_notified"):
        log.debug("%d unresolved review thread(s) still open; already notified the user",
                  len(threads))
    elif state.get("pr_thread_round", 0) >= config.PR_THREAD_MAX_ROUNDS:
        log.warning("review-thread round limit (%d) reached with %d open thread(s); "
                    "leaving them for the user", config.PR_THREAD_MAX_ROUNDS, len(threads))
        email(state, "unresolved review threads need your help",
              f"There are still {len(threads)} unresolved review conversation(s) on the PR "
              f"after {config.PR_THREAD_MAX_ROUNDS} round(s) of fixes.\nPR: {state['pr_url']}"
              "\n\nPlease resolve them yourself, or reply 'merge' to merge anyway.")
        state["pr_thread_notified"] = True
    else:
        state["pr_threads"] = threads
        state["state"] = "ADDRESS_PR_THREADS"
        log.info("PR has %d new unresolved review thread(s); addressing before merge", len(threads))
        return
    handle_wait(state)


# ---------------------------------------------------------------- abort / reset

def _abort_in_progress_ops() -> None:
    """Abort a half-finished merge/rebase/cherry-pick/am, if any. Checks git's own
    state files first so the no-op case stays silent instead of logging four
    "fatal: nothing in progress" errors every time."""
    git_dir = Path(git("rev-parse", "--absolute-git-dir"))
    checks = (
        (("merge", "--abort"), ["MERGE_HEAD"]),
        (("rebase", "--abort"), ["rebase-merge", "rebase-apply"]),
        (("cherry-pick", "--abort"), ["CHERRY_PICK_HEAD"]),
        (("am", "--abort"), ["rebase-apply/applying"]),
    )
    for op, markers in checks:
        if any((git_dir / m).exists() for m in markers):
            log.warning("git %s in progress; aborting it", op[0])
            _git_quiet(*op)


def _git_quiet(*args: str) -> bool:
    """Run a git command, returning success. Never raises — for the best-effort reset."""
    try:
        proc = subprocess.run(["git", *args], cwd=config.REPO_PATH, capture_output=True,
                              text=True, timeout=config.SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log.debug("git %s timed out after %ss", " ".join(args), config.SUBPROCESS_TIMEOUT_SECONDS)
        return False
    if proc.returncode != 0:
        log.debug("git %s -> rc=%d: %s", " ".join(args), proc.returncode, proc.stderr.strip()[:200])
    return proc.returncode == 0


def _reset_to_base_branch() -> list[str]:
    """Best-effort LOCAL reset: abort any half-finished git op, discard changes, land on a
    clean, up-to-date base branch. Never touches remote branches or PRs. Returns notes about
    any step that left the tree unclean (empty list when fully clean)."""
    _abort_in_progress_ops()  # a half-finished merge/rebase would block the checkout
    _git_quiet("reset", "--hard")                            # drop staged/unstaged tracked changes
    _git_quiet("checkout", "-f", config.BASE_BRANCH)         # leave whatever codebot branch we were on
    _git_quiet("clean", "-fd")             # drop untracked files; .gitignore (data/, .env) is kept
    # Branches may have merged/moved while we were away: fast-forward the local base branch to
    # the remote. Best-effort — a network failure here doesn't block the reset (do_pick pulls too).
    if _git_quiet("fetch", "origin", config.BASE_BRANCH):
        _git_quiet("reset", "--hard", f"origin/{config.BASE_BRANCH}")
    problems = []
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=config.REPO_PATH, capture_output=True, text=True, timeout=config.SUBPROCESS_TIMEOUT_SECONDS).stdout.strip()
    if branch != config.BASE_BRANCH:
        problems.append(f"could not switch to {config.BASE_BRANCH} (still on {branch or 'unknown'})")
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           cwd=config.REPO_PATH, capture_output=True, text=True, timeout=config.SUBPROCESS_TIMEOUT_SECONDS).stdout.strip()
    if dirty:
        problems.append("tracked changes remain after reset")
    return problems


# Every task-scoped state key. Cleared whenever a task ends (merge, DONE, abort) so the
# next pick starts from a clean slate. Keep in sync when adding state.
RESET_KEYS = ("item", "item_id", "item_url", "trail_ref", "item_detail", "item_images", "base_sha", "slug",
              "branch", "pending_question", "question_rounds", "stuck_return", "stuck_error", "failures", "session_id", "thread_id", "pr_url", "e2e_specs",
              "return_state", "review_since", "review_round", "review_run_link",
              "review_comment_watermark", "review_comments", "pr_summary", "pr_title",
              "pr_title_guidance",
              "pr_threads", "pr_thread_round", "pr_thread_notified", "verify_round",
              "review_gate_round", "archive_round", "archive_path", "e2e_repair_head",
              "e2e_repair_status", "push_context", "archive_error", "e2e_round",
              "review_threads", "await_new_run", "conflict_rounds", "conflict_return",
              "conflict_head", "stale_replies", "last_contact", "ping_count", "last_ping_at",
              "evidence_url")


def _finish_task(state: dict, note: str, reset_repo: bool) -> None:
    """End the task successfully: mark the item done in the backlog, optionally reset the
    checkout to a clean base branch (needed when finishing before a merge — the tree may
    hold proposal artifacts or a stale branch), email confirmation, and land in IDLE."""
    item = state.get("item", "")
    struck = task_source.mark_done(item, state.get("item_id")) if item else False
    if struck:
        log.info("marked item done in the backlog; task complete")
        body = f"{note}\n\nThe item was marked done in the backlog:\n\n{item}"
        subj = "task complete"
    else:
        log.warning("could not locate item in the backlog to mark done: %r", item[:80])
        # Also release the claim: a leftover self-claim would make do_pick's resume
        # filter re-pick this FINISHED task deterministically on the next idle tick,
        # long before the user can act on this email.
        try:
            task_source.unclaim_task(item, state.get("item_id"))
        except Exception:  # noqa: BLE001 — best-effort; the email below covers it
            log.exception("could not unclaim the unmatched item")
        subj = "task complete — mark the item manually"
        body = (f"{note}\n\nBut I could not find this item in the backlog to mark it "
                f"done:\n\n{item}\n\nPlease mark it done (or delete it) promptly "
                "— until then it may be picked again.")
    if reset_repo:
        problems = _reset_to_base_branch()
        if problems:
            body += ("\n\nThe repo reset finished with issues (I'll re-check before the "
                     "next task):\n- " + "\n- ".join(problems))
    body += "\n\nI'll pick up the next pending item from the backlog."
    email(state, subj, body)
    for key in RESET_KEYS:
        state.pop(key, None)
    state["state"] = "IDLE"


def _enter_stuck(state: dict, failed_state: str, detail: str) -> None:
    """Stop retrying, remember the failed state, e-mail the user, and enter WAIT_STUCK.

    The resume target lives in stuck_return, NOT return_state: return_state is the
    WAIT_REPLY phase pointer, and clobbering it here (e.g. when WAIT_REPLY itself
    escalates after repeated classifier failures) would strand the pending question —
    the answer would later resolve to an unknown phase and the task's context is lost."""
    state["stuck_return"] = failed_state
    state["stuck_error"] = detail[-2000:]
    email(state, f"stuck in {failed_state}",
          f"Task: {state.get('item', '?')}\nState: {failed_state}\n\n"
          f"I stopped and need your help.\n\n{detail}\n\n"
          "Reply 'retry' to try that step again, 'abort' to reset to a clean slate, "
          "'complete' to mark the task done as-is, or reply with instructions and I'll "
          "apply them and continue.")
    state["state"] = "WAIT_STUCK"


def _clear_stuck(state: dict, failed_state: str) -> None:
    # return_state is deliberately KEPT: when resuming WAIT_REPLY it still points at the
    # phase whose question is pending, and handle_result refreshes it on new questions.
    if "failures" in state:
        state["failures"].pop(failed_state, None)
    for counter in ("e2e_round", "verify_round", "review_gate_round", "archive_round",
                    "pr_thread_round"):
        if counter in state:
            state[counter] = 0
    state.pop("question_rounds", None)
    state.pop("conflict_rounds", None)
    state.pop("stuck_return", None)
    state.pop("stuck_error", None)


def _escalate(state: dict, failed_state: str) -> bool:
    """After the failure budget is exhausted for a state, e-mail the user and enter
    WAIT_STUCK. Returns True if the escalation was delivered. Never re-escalates WAIT_STUCK
    (its own failures just back off; ABORT is the escape hatch)."""
    if failed_state == "WAIT_STUCK":
        return False
    try:
        _enter_stuck(state, failed_state,
                     f"I've failed this step {config.MAX_STATE_FAILURES} times in a row. "
                     f"Last error:\n\n{traceback.format_exc()[-2000:]}")
        log.warning("escalated %s to WAIT_STUCK after %d failures",
                    failed_state, config.MAX_STATE_FAILURES)
        return True
    except Exception:
        log.exception("failed to escalate stuck state %s; will keep retrying", failed_state)
        return False


def do_stuck_reply(state: dict, reply: str) -> None:
    """Handle the user's reply while WAIT_STUCK: retry / abort / complete / instructions."""
    verdict = parse_json_reply(
        agent_runner.run(prompts.render(prompts.CLASSIFY_STUCK_REPLY, reply=reply),
                         contract=False).output)
    action = verdict.get("action")
    log.info("classified stuck reply as action=%r", action)
    failed_state = state.get("stuck_return", "IDLE")
    if action == "abort":
        _abort_and_reset(state, "Got it — I'm giving up on this task and resetting to a "
                                "clean slate.")
        return
    if action == "complete":
        _finish_task(state, "You asked me to mark the stuck task complete with no further "
                            "work.", reset_repo=True)
        return
    if action not in ("retry", "instructions"):
        email(state, "clarification needed",
              f"I could not tell whether you want me to retry, abort, or follow instructions:"
              f"\n\n{reply}\n\nPlease reply 'retry', 'abort', 'complete', or with explicit "
              "instructions.")
        return  # stay in WAIT_STUCK
    if action == "instructions" and failed_state == "OPEN_PR":
        # OPEN_PR is orchestrator-driven: the PR title/body never pass through the coding
        # session, so guidance about them must be applied HERE or it would be silently
        # ignored (a live incident: "use a shorter title" followed by the same failure).
        state["pr_title_guidance"] = (verdict.get("feedback") or reply)[:2000]
        state.pop("pr_title", None)
        log.info("recorded PR title guidance; the title is regenerated on resume")
    if action == "instructions" and state.get("session_id"):
        # Apply the guidance in the working session, then let the failed state re-run — which
        # handles any follow-up question through its own do_* handler.
        log.info("applying user instructions to session before resuming %s", failed_state)
        result = agent_runner.resume(state["session_id"], prompts.render(
            prompts.ANSWER_REPLY, reply=verdict.get("feedback") or reply,
            rules=prompts.PHASE_RULES.get(failed_state, "")))
        state["session_id"] = result.session_id
    # retry, or instructions applied: clear the failure history for the state and resume it.
    _clear_stuck(state, failed_state)
    if failed_state == "IDLE":
        # The unrecoverable-context fallback resumes at IDLE, which means "no task":
        # drop every task key so session/PR/spec state can't leak into the next pick.
        for key in RESET_KEYS:
            state.pop(key, None)
    state["state"] = failed_state


def _abort_and_reset(state: dict, note: str, new_thread: bool = False) -> None:
    """Shared abort machinery: reset the local checkout, email a confirmation, clear all
    task state, and return to IDLE. Used both by the mailbox-wide last-resort 'ABORT'
    email and by an explicit abort classified from a WAIT_APPROVAL/WAIT_MERGE reply.
    Never touches remote branches or PRs — those are left for the user to clean up."""
    aborted_task = state.get("item", "-")
    prev_state = state["state"]
    log.warning("ABORT: resetting to IDLE (was state=%s task=%r)", prev_state, aborted_task[:80])
    problems = _reset_to_base_branch()
    # The task goes back to the pool, so its claim marker must go too — otherwise no
    # instance (including this one, if its state was wiped) would ever pick it again.
    if aborted_task and aborted_task != "-":
        try:
            if not task_source.unclaim_task(aborted_task, state.get("item_id")):
                problems.append("could not find the backlog item to release its "
                                "claim — release it manually")
        except Exception:  # noqa: BLE001 — a backlog hiccup must not block the reset
            log.exception("unclaim failed during reset")
            problems.append("could not release the item's claim in the backlog — "
                            "release it manually or no instance will pick the task")
    status = (f"The working tree was reset to a clean, up-to-date `{config.BASE_BRANCH}`." if not problems
              else "The reset finished with issues (I'll re-check the tree before starting the "
                   "next task):\n- " + "\n- ".join(problems))
    email(state, "aborted — reset to IDLE",
          f"{note}\n\nWas working on: {aborted_task}\nPrevious state: {prev_state}\n\n{status}\n\n"
          "Remote branches and PRs were left untouched. I'll pick up the next pending item "
          "from the backlog.", new_thread=new_thread)
    for key in RESET_KEYS:
        state.pop(key, None)
    state["state"] = "IDLE"


# ---------------------------------------------------------------- on-hold tasks

def _load_holds() -> list[dict]:
    try:
        return json.loads(config.HOLDS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return []


def _save_holds(holds: list[dict]) -> None:
    tmp = config.HOLDS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(holds, indent=2))
    tmp.replace(config.HOLDS_PATH)


def _commit_pending_work(state: dict) -> list[str]:
    """Leave nothing dangling before parking a task: abort any half-finished git
    operation, then commit every tracked change and every untracked file that is not
    evidence on the task branch. Returns notes about anything that could not be saved."""
    notes = []
    branch = state.get("branch")
    if not branch:
        return notes
    _abort_in_progress_ops()
    if git("rev-parse", "--abbrev-ref", "HEAD") != branch:
        if not _git_quiet("checkout", branch):
            notes.append(f"could not switch back to {branch} to save pending work")
            return notes
    _git_quiet("add", "-u")  # every tracked change
    untracked = [p for p in git("ls-files", "--others", "--exclude-standard").splitlines()
                 if p.strip()]
    kept = [p for p in untracked if not _looks_like_evidence(p)]
    if kept:
        _git_quiet("add", "--", *kept)
    if git("status", "--porcelain", "--untracked-files=no"):
        if _git_quiet("commit", "-q", "-m", "wip: task put on hold by the user"):
            notes.append("committed pending work as 'wip: task put on hold by the user'")
        else:
            notes.append("could not commit the pending work — it stays in the working tree")
    return notes


def _hold_task(state: dict, thread_id: str | None) -> None:
    """Park the current task: save its work and state, mark it on hold in the backlog,
    and return to IDLE so the next task can start. CONTINUE on the task's thread
    brings it back with top priority."""
    item = state.get("item", "")
    notes = _commit_pending_work(state)
    try:
        if not task_source.hold_task(item, state.get("item_id")):
            notes.append("could not mark the item on hold in the backlog — another "
                         "instance may pick it up; mark it on hold by hand")
    except Exception:  # noqa: BLE001 — a backlog hiccup must not lose the hold
        log.exception("hold marker failed")
        notes.append("could not update the backlog (see logs)")
    resume_state = state["state"]
    saved = {k: state[k] for k in RESET_KEYS if k in state}
    saved["state"] = resume_state
    holds = [h for h in _load_holds() if h.get("thread_id") != state.get("thread_id")]
    holds.append({"thread_id": state.get("thread_id") or thread_id, "item": item,
                  "item_id": state.get("item_id"),
                  "slug": state.get("slug"), "branch": state.get("branch"),
                  "held_at": time.time(), "requested": False, "note": "", "saved": saved})
    _save_holds(holds)
    body = (f"Task on hold: {item}\nBranch: {state.get('branch', '-')} (all work "
            f"committed there)\nIt was in state {resume_state}.\n\n"
            "I'm moving on to the next backlog item. Reply 'continue' on THIS thread "
            "(optionally followed by instructions) and I'll pick this task back up "
            "first thing after my current work.")
    if notes:
        body += "\n\nNotes:\n- " + "\n- ".join(notes)
    email(state, "on hold", body)
    problems = _reset_to_base_branch()
    if problems:
        log.warning("reset after hold left issues: %s", problems)
    for key in RESET_KEYS:
        state.pop(key, None)
    state["state"] = "IDLE"
    log.info("task on hold: %r (resume at %s)", item[:80], resume_state)


def _request_continue(thread_id: str, note: str) -> bool:
    """Flag the held task on this thread as requested; it is restored at the next pick.
    False when no held task lives on the thread."""
    holds = _load_holds()
    for hold in holds:
        if hold.get("thread_id") == thread_id:
            hold["requested"] = True
            hold["note"] = note
            hold["requested_at"] = time.time()
            _save_holds(holds)
            log.info("continue requested for held task %r", hold.get("item", "")[:80])
            return True
    return False


def _resume_held_task(state: dict, hold: dict) -> None:
    """Restore a held task into `state` (branch, session, wait/phase state) and apply
    the user's CONTINUE note, if any, as the reply the task was waiting for."""
    saved = dict(hold.get("saved") or {})
    resume_state = saved.pop("state", "EXPLORING")
    note = hold.get("note", "")
    item = hold.get("item", "")
    log.info("resuming held task %r at %s", item[:80], resume_state)
    item_id = hold.get("item_id")
    try:
        task_source.unhold_task(item, item_id)
    except Exception:  # noqa: BLE001
        log.exception("could not remove the hold marker")
    if not task_source.claim_task(item, item_id):
        log.warning("held task could not be re-claimed (struck or claimed elsewhere); dropping "
                    "the hold: %r", item[:80])
        _save_holds([h for h in _load_holds() if h is not hold and h.get("thread_id") != hold.get("thread_id")])
        return
    branch = hold.get("branch") or saved.get("branch")
    if branch:
        git("checkout", branch)
    state.update(saved)
    state["state"] = resume_state
    _save_holds([h for h in _load_holds() if h.get("thread_id") != hold.get("thread_id")])
    if note and state["state"] in WAITS and state["state"] != "WAIT_REVIEW":
        # The note answers whatever the task was waiting on (approval, question, merge).
        email(state, "resumed", f"Resuming this task with your note:\n\n{note}")
        _handle_reply(state, note)
        return
    if note and state.get("session_id"):
        result = agent_runner.resume(state["session_id"], prompts.render(
            prompts.ANSWER_REPLY, reply=f"(task resumed after a pause) {note}",
            rules=prompts.PHASE_RULES.get(state["state"], "")))
        if handle_result(state, result, state["state"]):
            return
    last = state.get("last_email") or {}
    if state["state"] in WAITS:
        email(state, "resumed",
              "Resuming this task; I'm still waiting on your reply to my last message"
              + (f":\n\n{last.get('body', '')}" if last.get("body") else "."))
    else:
        email(state, "resumed", f"Resuming this task from state {state['state']}.")


def _is_transient_network_error(error: BaseException) -> bool:
    """A network blip talking to Gmail/GitHub (TLS EOF, connection reset, DNS, timeout,
    5xx/429), as opposed to a fault in the state being executed."""
    if isinstance(error, (ssl.SSLError, ConnectionError, TimeoutError,
                          socket.gaierror, socket.herror)):
        return True
    if type(error).__module__.startswith("httplib2"):  # ServerNotFoundError & co.
        return True
    status = getattr(getattr(error, "resp", None), "status", None)  # googleapiclient HttpError
    return status in (429, 500, 502, 503, 504)


def check_commands(state: dict) -> bool:
    """Handle a mailbox-wide user command (ABORT / STATUS / DONE). Returns True only when
    the tick should skip normal dispatch (an ABORT reset or a DONE completion).

    Checked every tick regardless of state and mailbox-wide, so it works even when the agent
    is stuck waiting on a thread — or in a state that never polls the inbox (WAIT_REVIEW).
    Only commands from CODEBOT_USER_EMAIL are honored. A gmail hiccup here must not break
    the tick, so polling failures are swallowed. ABORT and DONE reset local state only —
    remote branches and PRs are untouched.
    """
    try:
        polled = gmail_client.poll_command()
    except Exception as error:
        if _is_transient_network_error(error):
            log.warning("command check could not poll gmail (%s: %s); skipping this tick",
                        type(error).__name__, error)
        else:
            log.exception("command check could not poll gmail; skipping this tick")
        return False
    if polled is None:
        return False
    msg_id, thread_id, command, targeted, note = polled
    if command == "CONTINUE":
        if not _request_continue(thread_id, note):
            if thread_id and thread_id == state.get("thread_id"):
                # "continue" on the ACTIVE task thread is ordinary conversation
                # ("carry on"); leave it for handle_wait's classifiers.
                log.debug("CONTINUE-shaped reply on the active thread; deferring")
                return False
            gmail_client.mark_processed(msg_id)
            gmail_client.send(f"{config.SUBJECT_PREFIX} general — nothing on hold here",
                              "CONTINUE received, but no task is on hold on this thread.",
                              thread_id)
            return False
        gmail_client.mark_processed(msg_id)
        gmail_client.send(f"{config.SUBJECT_PREFIX} general — will continue",
                          "Got it — this task is next: I'll resume it as soon as my current "
                          "work is done (right away if I'm idle).", thread_id)
        return False
    if command == "HOLD":
        if not state.get("item"):
            log.warning("HOLD command received but no task is in progress; ignoring")
            gmail_client.mark_processed(msg_id)
            gmail_client.send(f"{config.SUBJECT_PREFIX} general — nothing to hold",
                              "HOLD received, but no task is in progress.", thread_id)
            return False
        # Consume only AFTER handling (multi-step side effects, like DONE).
        _hold_task(state, thread_id)
        gmail_client.mark_processed(msg_id)
        return True
    if command == "DONE":
        if not targeted and thread_id and thread_id == state.get("thread_id"):
            # A BARE "Done"-bodied reply on the ACTIVE task thread is normal
            # conversation ("Done" = "I did what you asked"), not the command — leave
            # it unprocessed for handle_wait and its classifiers. "DONE <this-instance>"
            # is explicit and IS the command.
            log.debug("bare DONE-shaped reply on the active thread; deferring to the "
                      "thread classifier")
            return False
        if not state.get("item"):
            log.warning("DONE command received but no task is in progress; ignoring")
            gmail_client.mark_processed(msg_id)
            gmail_client.send(f"{config.SUBJECT_PREFIX} general — nothing to complete",
                              "DONE received, but no task is in progress.", thread_id)
            return False
        # Consume only AFTER handling: _finish_task has multi-step network side effects
        # (docs strike-through, repo reset, email); a failure mid-way must leave the
        # DONE unprocessed so the next tick retries it. Each step is idempotent enough
        # to re-run (a struck item just reports "mark manually" on the retry).
        _finish_task(state, "DONE command received: marking the current task complete.",
                     reset_repo=True)
        gmail_client.mark_processed(msg_id)
        return True
    # ABORT / STATUS: consume the trigger first — handling is idempotent, and marking it
    # processed up front guarantees a failure afterwards can't loop us into re-running it.
    gmail_client.mark_processed(msg_id)
    if command == "STATUS":
        _send_status(state, thread_id)
        if thread_id and thread_id == state.get("thread_id"):
            _note_contact(state)  # a STATUS exchange on the task thread is contact too
        return False  # STATUS is read-only; let the tick proceed normally
    _abort_and_reset(state, "ABORT received: I stopped the task in progress and reset myself "
                            "to a clean slate.", new_thread=True)
    return True


def _fmt_ts(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(epoch))


def _heartbeat_age() -> float | None:
    try:
        return time.time() - config.HEARTBEAT_PATH.stat().st_mtime
    except OSError:
        return None


def _send_status(state: dict, thread_id: str) -> None:
    """Reply to a STATUS command with a snapshot of the FSM. Never mutates state."""
    lines = [
        f"Instance: {config.INSTANCE_ID}",
        f"State: {state.get('state', '?')}",
        f"Task: {state.get('item', '-')}",
        f"Slug: {state.get('slug', '-')}",
        f"Branch: {state.get('branch', '-')}",
        f"PR: {state.get('pr_url', '-')}",
    ]
    if state.get("stuck_return"):
        lines.append(f"Stuck on state (awaiting your reply): {state['stuck_return']}")
    if state.get("return_state"):
        lines.append(f"Pending question from phase: {state['return_state']}")
    if state.get("stuck_error"):
        lines.append(f"Last error:\n{state['stuck_error']}")
    active = {k: v for k, v in state.get("failures", {}).items() if v}
    if active:
        lines.append("Failure counters: " + ", ".join(f"{k}={v}" for k, v in active.items()))
    if state.get("question_rounds"):
        lines.append(f"Consecutive question rounds: {state['question_rounds']}")
    if state.get("conflict_rounds"):
        lines.append(f"Merge-conflict resolution attempts: {state['conflict_rounds']}")
    age = _heartbeat_age()
    if age is not None:
        lines.append(f"Heartbeat age: {age:.0f}s")
    holds = _load_holds()
    if holds:
        lines.append("On hold: " + "; ".join(
            f"{h.get('slug') or h.get('item', '?')[:40]}"
            + (" (continue requested)" if h.get("requested") else "") for h in holds))
    if state.get("last_transition"):
        lines.append(f"Last transition: {_fmt_ts(state['last_transition'])}")
    if state.get("last_contact") is not None:
        lines.append(f"Last real email on the task thread: {_fmt_ts(state['last_contact'])}")
    if state.get("ping_count"):
        lines.append(f"Silence check-ins sent since then: {state['ping_count']} "
                     f"(last at {_fmt_ts(state['last_ping_at'])})")
    for key, label in (("e2e_round", "E2E fix rounds"), ("verify_round", "Quality-gate rounds"),
                       ("review_round", "Code-review rounds"),
                       ("pr_thread_round", "PR-thread rounds"), ("archive_round", "Archive rounds")):
        if state.get(key):
            lines.append(f"{label}: {state[key]}")
    body = "codebot status:\n\n" + "\n".join(lines)
    last = state.get("last_email")
    if last:
        body += (f"\n\n--- Last email sent ({_fmt_ts(last['sent_at'])}) ---\n"
                 f"Subject: {last['subject']}\n\n{last['body']}")
    subj = f"{config.SUBJECT_PREFIX} {state.get('slug', 'general')} — status"
    gmail_client.send(subj, body, thread_id)
    log.info("sent STATUS report (state=%s)", state.get("state"))


# What "this phase finished via a WAIT_REPLY answer" means, per phase. Mirrors each
# do_* function's own success tail so a phase completed through a question detour ends
# up in exactly the same place as one completed directly.
def _continue_exploring(state: dict, result) -> None:
    _undo_premature_work(state, "EXPLORING")
    state["state"] = "PROPOSING"


def _continue_proposing(state: dict, result) -> None:
    note = _undo_premature_work(state, "PROPOSING")
    email(state, "proposal for review",
          f"{result.output}\n\n" + (f"{note}\n\n" if note else "")
          + "Reply with your approval or requested changes.")
    state["state"] = "WAIT_APPROVAL"


def _continue_implementing(state: dict, result) -> None:
    if _scrub_evidence_from_repo(state, "IMPLEMENTING") is None:
        return
    # The direct path parses the spec list from the final output; an answer that
    # completes the phase carries the same contract, so parse it here too.
    specs = evidence.reported_specs(result.output)
    if specs:
        state["e2e_specs"] = specs
        log.info("implementation (via reply) reported %d e2e spec(s): %s", len(specs), specs)
    state["e2e_round"] = 0
    state["verify_round"] = 0
    state["state"] = "VERIFYING"
    trail(state, "Implementation complete; verifying")


def _continue_verifying(state: dict, result) -> None:
    state["verify_round"] = 0  # the user's guidance earns a fresh set of attempts
    _complete_verify(state, result)


def _continue_internal_review(state: dict, result) -> None:
    state["review_gate_round"] = 0
    _complete_internal_review(state, result)


def _continue_e2e(state: dict, result) -> None:
    state["e2e_round"] = 0  # the user's guidance earns a fresh set of attempts
    if "e2e_repair_head" in state and "e2e_repair_status" in state:
        _finish_e2e_repair(state)
    else:
        state["state"] = "E2E"  # re-run the suite on the (answer-informed) fix


def _continue_archiving(state: dict, result) -> None:
    state["archive_round"] = 0
    state["state"] = "ARCHIVING"


def _continue_address_review(state: dict, result) -> None:
    # Whether the answer-informed session committed is unknown on this detour path
    # (no head snapshot): push regardless — a no-op push is harmless, and the review
    # wait then either sees a new run or concludes from the clean-check.
    _finish_address_review(state, result, head_before=None)


def _continue_resolve_conflicts(state: dict, result) -> None:
    # conflict_head was persisted when the resolution session started, so this detour
    # can make the same committed-or-not exit decision as the direct path.
    _leave_conflict_resolution(state)


def _continue_address_pr_threads(state: dict, result) -> None:
    if _scrub_evidence_from_repo(state, "ADDRESS_PR_THREADS") is None:
        return
    _queue_push(state, "threads")


def _continue_apply_pr_feedback(state: dict, result) -> None:
    extra_attachments = _scrub_evidence_from_repo(state, "APPLY_PR_FEEDBACK")
    if extra_attachments is None:
        return
    attachments = _collect_attachments(
        result, state.get("e2e_specs", []), state.get("e2e_kind"))
    existing = {path.resolve() for path in attachments}
    attachments += [path for path in extra_attachments if path.resolve() not in existing]
    _queue_push(state, "feedback", result.output, attachments)


CONTINUATIONS = {
    "EXPLORING": _continue_exploring,
    "PROPOSING": _continue_proposing,
    "IMPLEMENTING": _continue_implementing,
    "VERIFYING": _continue_verifying,
    "INTERNAL_REVIEW": _continue_internal_review,
    "E2E": _continue_e2e,
    "ARCHIVING": _continue_archiving,
    "ADDRESS_REVIEW": _continue_address_review,
    "ADDRESS_PR_THREADS": _continue_address_pr_threads,
    "APPLY_PR_FEEDBACK": _continue_apply_pr_feedback,
    "RESOLVE_CONFLICTS": _continue_resolve_conflicts,
}


def _reply_prompt(state: dict, phase: str, reply: str) -> str:
    """The prompt that resumes the working session with the user's answer. Gate phases
    re-issue their own contract prompt (the answer alone would not make the session emit
    the completion contract again); every other phase gets the answer plus its rules."""
    if phase in ("VERIFYING", "INTERNAL_REVIEW"):
        gate_prompt = _verify_prompt if phase == "VERIFYING" else _internal_review_prompt
        return f"User recovery guidance:\n{reply}\n\n" + gate_prompt(state)
    if phase == "ARCHIVING":
        return prompts.render(prompts.FIX_ARCHIVE,
                              error=state.get("archive_error", "unknown archival failure"),
                              guidance=reply)
    return prompts.render(prompts.ANSWER_REPLY, reply=reply,
                          rules=prompts.PHASE_RULES.get(phase, ""))


def do_question_reply(state: dict, reply: str) -> None:
    """Handle the user's answer while WAIT_REPLY. The reply is classified first — with a
    fresh session, like the other waits — because control-flow instructions ("mark it
    done and move on", "abandon this") must act on the FSM, not be forwarded to the
    working session, which has no lever on the FSM and can only loop asking questions."""
    verdict = parse_json_reply(
        agent_runner.run(
            prompts.render(prompts.CLASSIFY_QUESTION_REPLY, reply=reply,
                           question=state.get("pending_question", "(not recorded)")),
            contract=False).output)
    action = verdict.get("action")
    log.info("classified WAIT_REPLY reply as action=%r", action)
    if action == "complete":
        _finish_task(state, "You asked me to mark this task complete with no further work.",
                     reset_repo=True)
        return
    if action == "abort":
        _abort_and_reset(state, "Got it — I'm stopping this task and resetting to a clean slate.")
        return
    # answer (the default): resume the working session, restating the phase rules the
    # raw reply lacks — sessions have overreached (implemented/pushed while PROPOSING)
    # exactly on these unframed resumes.
    # Read return_state without popping: if a later step here raises, the state stays
    # WAIT_REPLY with return_state intact so the retry re-runs cleanly.
    phase = state.get("return_state")
    if phase not in CONTINUATIONS:
        _enter_stuck(state, "IDLE",
                     f"Internal error: I was waiting on a question for unknown phase "
                     f"{phase!r} and cannot resume it. 'retry' restarts from the backlog; "
                     "'abort' resets me.")
        return
    trail(state, f"Answer received (resuming {phase})", reply)
    result = agent_runner.resume(state["session_id"], _reply_prompt(state, phase, reply))
    if handle_result(state, result, phase):
        return  # re-questioned (or question cap hit); return_state already updated
    CONTINUATIONS[phase](state, result)
    if state["state"] != "WAIT_REPLY":  # a continuation may itself have re-questioned
        state.pop("return_state", None)
        state.pop("pending_question", None)


def _handle_reply(state: dict, reply: str) -> None:
    if state["state"] == "WAIT_APPROVAL":
        do_approval_reply(state, reply)
    elif state["state"] == "WAIT_STUCK":
        do_stuck_reply(state, reply)
    elif state["state"] == "WAIT_MERGE":
        do_merge_reply(state, reply)
    elif state["state"] == "WAIT_CLEAN":
        state["state"] = "IDLE"
    elif state["state"] == "WAIT_REPLY":
        do_question_reply(state, reply)


# Loop liveness for the heartbeat thread: the main loop stamps this at the start of every
# tick. The daemon touches the heartbeat file only while a tick is younger than the max
# plausible duration, so a legit multi-hour agent call stays healthy but a wedged loop
# eventually lets the heartbeat go stale (see config.HEARTBEAT_MAX_TICK_SECONDS).
_liveness = {"tick_started": time.time()}
_lock_handle = None  # kept alive for the process lifetime so the flock is held


def _heartbeat_loop() -> None:
    while True:
        try:
            if time.time() - _liveness["tick_started"] < config.HEARTBEAT_MAX_TICK_SECONDS:
                config.HEARTBEAT_PATH.write_text(str(int(time.time())))
        except Exception:
            log.exception("heartbeat write failed")
        time.sleep(config.POLL_INTERVAL_SECONDS)


class ShutdownRequested(BaseException):
    """Raised in the main thread by the SIGTERM/SIGINT handler. A BaseException (not
    Exception) so it passes through every `except Exception` in the phases, and so
    subprocess.run() kills whatever child is running (an agent call, e2e, git) on its
    way out instead of waiting for it."""


def _request_shutdown(signum, _frame) -> None:
    raise ShutdownRequested(signal.Signals(signum).name)


def _install_shutdown_handlers() -> None:
    """Python is PID 1 in the container and has no default SIGTERM handler there, so a
    plain `docker stop` (Spot interruption, host shutdown, redeploy) would be ignored
    until Docker SIGKILLs us. With the handler we drop everything at once and exit;
    the last completed tick is already on disk, so the next start resumes from it."""
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)


def _release_single_instance_lock() -> None:
    global _lock_handle
    if _lock_handle is not None:
        try:
            _lock_handle.close()
        except OSError:
            pass
        _lock_handle = None


def _acquire_single_instance_lock() -> None:
    """Refuse to start a second codebot against the same data/ dir — two processes would
    interleave state.json writes. The lock is released automatically when the process exits."""
    global _lock_handle
    lock_path = config.DATA_DIR / "state.lock"
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _lock_handle = open(lock_path, "w")
    try:
        fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(f"another codebot already holds {lock_path}; refusing to start")


def validate_managed_runtime() -> None:
    required = [
        ("Superpowers skill tree",
         config.SUPERPOWERS_PLUGIN_DIR / "skills/using-superpowers/SKILL.md"),
        ("bridge manifest", config.BRIDGE_PLUGIN_DIR / ".claude-plugin/plugin.json"),
        ("bridge skill",
         config.BRIDGE_PLUGIN_DIR / "skills/coderbot-openspec-workflow/SKILL.md"),
    ]
    if config.AGENT == "claude":
        required.append(("Superpowers Claude manifest",
                         config.SUPERPOWERS_PLUGIN_DIR / ".claude-plugin/plugin.json"))
    elif config.AGENT == "opencode":
        required.extend([
            ("Superpowers OpenCode entrypoint",
             config.SUPERPOWERS_PLUGIN_DIR / ".opencode/plugins/superpowers.js"),
            ("bridge OpenCode package", config.BRIDGE_PLUGIN_DIR / "package.json"),
            ("bridge OpenCode entrypoint",
             config.BRIDGE_PLUGIN_DIR / ".opencode/plugins/coderbot-openspec.js"),
        ])

    for label, path in required:
        if not path.is_file():
            raise SystemExit(f"managed runtime unavailable: missing {label} at {path}")


def main() -> None:
    if config.AGENT not in ("claude", "opencode"):
        raise SystemExit("CODEBOT_AGENT must be 'claude' or 'opencode'")
    if config.AGENT == "opencode" and (
            "/" not in config.OPENCODE_MODEL or config.OPENCODE_MODEL.endswith("/")):
        raise SystemExit("OPENCODE_MODEL must be set to provider/model when CODEBOT_AGENT=opencode")
    validate_managed_runtime()
    if not config.USER_EMAIL:
        raise SystemExit("CODEBOT_USER_EMAIL must be set in .env")
    if config.TASK_SOURCE not in task_source.SOURCES:
        raise SystemExit("CODEBOT_TASK_SOURCE must be one of: " + ", ".join(task_source.SOURCES))
    if config.TASK_SOURCE == "gdoc" and not config.DOC_ID:
        raise SystemExit("CODEBOT_DOC_ID must be set in .env (the backlog Google Doc id)")
    if config.TASK_SOURCE == "github" and not (config.GH_PROJECT_OWNER and config.GH_PROJECT_NUMBER):
        raise SystemExit("CODEBOT_GH_PROJECT_URL (or CODEBOT_GH_PROJECT_OWNER and "
                         "CODEBOT_GH_PROJECT_NUMBER) must be set in .env when "
                         "CODEBOT_TASK_SOURCE=github")
    # .exists() not .is_dir(): in a git worktree .git is a file.
    if not (config.REPO_PATH / ".git").exists():
        raise SystemExit(
            f"CODEBOT_REPO_PATH ({config.REPO_PATH}) is not a git checkout; set it in .env")
    try:
        task_source.validate()
    except RuntimeError as err:
        raise SystemExit(f"backlog ({config.TASK_SOURCE}) unavailable: {err}") from err
    _acquire_single_instance_lock()
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    log.info("codebot starting; instance=%s agent=%s repo=%s source=%s %s",
             config.INSTANCE_ID, config.AGENT, config.REPO_PATH, config.TASK_SOURCE,
             task_source.describe())
    # Re-assert the backlog claim for an in-flight task: one picked before claim markers
    # existed (or whose marker was hand-deleted) is invisible protection-wise, and a
    # newly spawned instance could pick it too. Best-effort — a claim now held by
    # ANOTHER instance is only logged (claim_task does); the user sorts out that
    # pre-existing split-brain.
    try:
        startup_state = load_state()
        if startup_state.get("item"):
            task_source.claim_task(startup_state["item"], startup_state.get("item_id"))
    except Exception:  # noqa: BLE001 — an unreachable backlog must not block startup
        log.exception("could not re-assert the in-flight task's claim at startup")
    _install_shutdown_handlers()
    try:
        _run_loop()
    except ShutdownRequested as sig:
        # Deliberately no save_state: the tick in flight may have half-mutated the
        # state dict, while state.json still holds the last completed tick (phases
        # that need a mid-tick checkpoint save one themselves). Resuming from that
        # re-runs the interrupted phase, which is the same recovery as a crash.
        log.info("received %s; stopping (the in-flight tick is discarded, state.json "
                 "keeps the last completed one)", sig)
    finally:
        _release_single_instance_lock()


def _run_loop() -> None:
    backoff = config.POLL_INTERVAL_SECONDS
    while True:
        _liveness["tick_started"] = time.time()
        try:
            state = load_state()
        except (json.JSONDecodeError, OSError):
            # Corrupt/unreadable state.json: don't crash the process — log and wait
            # so an operator can repair or delete the file.
            log.exception("could not read %s; retrying in %ss", config.STATE_PATH,
                          config.POLL_INTERVAL_SECONDS)
            time.sleep(config.POLL_INTERVAL_SECONDS)
            continue
        prev = state["state"]
        try:
            log.debug("tick: state=%s task=%r", prev, state.get("item", "-"))
            if check_commands(state):
                pass  # reset to IDLE; skip normal dispatch this tick
            elif state["state"] == "WAIT_REVIEW" and check_pr_conflicts(state):
                pass  # the base branch moved and conflicted the PR; rerouted to
                # RESOLVE_CONFLICTS (or WAIT_STUCK) and dispatched next tick
            elif state["state"] == "WAIT_REVIEW":
                handle_review_wait(state)
            elif state["state"] == "WAIT_MERGE":
                # A pending reply speaks to the CURRENT PR and is consumed first —
                # do_merge_reply handles CONFLICTING itself. Only a reply-less tick
                # watches for a conflict, so a reply is never silently carried across
                # a conflict detour.
                handle_merge_wait(state)
                if state["state"] == "WAIT_MERGE":
                    check_pr_conflicts(state)
            elif state["state"] in WAITS:
                handle_wait(state)
            else:
                PHASES[state["state"]](state)
            # Success: clear this state's consecutive-failure counter.
            if state.get("failures", {}).get(prev):
                state["failures"][prev] = 0
            if state["state"] != prev:
                log.info("state transition: %s -> %s", prev, state["state"])
                state["last_transition"] = time.time()
            _maybe_ping(state)
            save_state(state)
            backoff = config.POLL_INTERVAL_SECONDS
        except Exception as error:
            if _is_transient_network_error(error):
                # A network blip is not a fault of this state: one line, no traceback,
                # and no progress toward the WAIT_STUCK escalation.
                log.warning("cycle failed in %s on a transient network error (%s: %s); "
                            "retrying in %ss", prev, type(error).__name__, error, backoff)
            else:
                failures = state.setdefault("failures", {})
                failures[prev] = failures.get(prev, 0) + 1
                log.exception("cycle failed in %s (%d/%d); retrying in %ss",
                              prev, failures[prev], config.MAX_STATE_FAILURES, backoff)
                if failures[prev] >= config.MAX_STATE_FAILURES and _escalate(state, prev):
                    if state["state"] != prev:
                        state["last_transition"] = time.time()
                    save_state(state)
                    backoff = config.POLL_INTERVAL_SECONDS
                    time.sleep(config.POLL_INTERVAL_SECONDS)
                    continue
            _maybe_ping(state)  # a failing step is exactly when "is it stuck?" gets asked
            save_state(state)
            time.sleep(backoff)
            backoff = min(backoff * 2, 3600)
            continue
        if state["state"] in WAITS or state["state"] == "IDLE":
            time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
