"""Central configuration for codebot. Everything env-overridable."""
import os
import re
import secrets
from pathlib import Path

CODEBOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CODEBOT_DATA_DIR", CODEBOT_DIR / "data"))


def _instance_id() -> str:
    """This installation's stable identity, for multi-instance coordination. It tags
    email subjects and git branches, names this instance in the backlog doc's
    "[implementing: <instance>]" claim markers, and scopes mailbox commands.

    Every clone of the repo runs the SAME compose file and .env, so identity cannot
    come from configuration: it is generated once per installation and persisted in
    data/instance_id (per-clone, survives restarts). CODEBOT_INSTANCE overrides it
    for a hand-picked name. Sanitized to [a-z0-9-] because branch names and the
    claim-marker regex build on it."""
    explicit = (os.environ.get("CODEBOT_INSTANCE") or "").strip().lower()
    if explicit:
        # Collapse runs and strip edge dashes: git rejects refnames starting with "-",
        # and branches are built as "<id>-<slug>".
        cleaned = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", explicit)).strip("-")
        return cleaned or "codebot"
    path = DATA_DIR / "instance_id"
    try:
        saved = path.read_text().strip().lower()
    except OSError:
        saved = ""
    if saved and re.fullmatch(r"[a-z0-9-]+", saved):
        return saved
    # Unambiguous alphabet (no 0/o, 1/l/i): these ids appear in email subjects and
    # commands the user types back ("ABORT codebot-x7k2").
    generated = "codebot-" + "".join(
        secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(4))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(generated + "\n")
    return generated


INSTANCE_ID = _instance_id()

# Backlog Google Doc. Required — set CODEBOT_DOC_ID in .env (validated in main()).
DOC_ID = os.environ.get("CODEBOT_DOC_ID", "")
# When set, only tasks under this heading in the backlog doc are offered to PICK; bullets
# under any other heading (e.g. items still under discussion) are not worked on. Empty
# (the default) means every top-level bullet in the doc is a candidate.
DOC_SECTION = os.environ.get("CODEBOT_DOC_SECTION") or ""
# May be a comma-separated list: mail is SENT to the first address; mail FROM any of
# them is trusted as the user (replies, approvals, ABORT/STATUS/DONE commands).
USER_EMAIL = os.environ.get("CODEBOT_USER_EMAIL", "")
# Target git checkout the agent works on. Required in the container (compose and
# entrypoint enforce it; main() validates it's a git repo). The sentinel default
# keeps host-side imports (setup_oauth.py) working without env vars.
REPO_PATH = Path(os.environ.get("CODEBOT_REPO_PATH") or "/unset-CODEBOT_REPO_PATH")
# Human-readable project name used in prompts; defaults to the repo dir name.
PROJECT_NAME = os.environ.get("CODEBOT_PROJECT_NAME") or REPO_PATH.name

# Branch codebot syncs from before picking a task, branches feature work off of, opens
# PRs against, and resets to on abort. Defaults to "main" for repos that use it as their
# trunk; set to "develop" or similar for repos with a different trunk convention.
BASE_BRANCH = os.environ.get("CODEBOT_BASE_BRANCH") or "main"

# The coding CLI used for autonomous work. Claude remains the default so existing
# deployments continue to work without changing their .env file.
AGENT = os.environ.get("CODEBOT_AGENT") or "claude"

# `or` (not a get-default) so an empty env value from .env still falls back,
# rather than passing --model "" to the claude CLI.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or "claude-fable-5"
CLAUDE_EFFORT = os.environ.get("CLAUDE_EFFORT") or "medium"
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL") or ""

SUPERPOWERS_VERSION = "v6.3.0"
SUPERPOWERS_PLUGIN_DIR = Path(os.environ.get(
    "CODEBOT_SUPERPOWERS_PLUGIN_DIR") or "/opt/coderbot/plugins/node_modules/superpowers")
BRIDGE_PLUGIN_DIR = Path(os.environ.get(
    "CODEBOT_BRIDGE_PLUGIN_DIR") or "/opt/coderbot/agent-plugin")

# DEBUG surfaces per-email/video/git detail in `docker compose logs`.
LOG_LEVEL = (os.environ.get("CODEBOT_LOG_LEVEL") or "DEBUG").upper()

POLL_INTERVAL_SECONDS = int(os.environ.get("CODEBOT_POLL_INTERVAL", "120"))
# CODEBOT_CLAUDE_TIMEOUT is retained as a fallback for existing installations.
AGENT_TIMEOUT_SECONDS = int(os.environ.get(
    "CODEBOT_AGENT_TIMEOUT", os.environ.get("CODEBOT_CLAUDE_TIMEOUT", "7200")))
E2E_TIMEOUT_SECONDS = int(os.environ.get("CODEBOT_E2E_TIMEOUT", "3600"))
# Short calls (git/gh) must never hang the tick loop; a timeout surfaces as a tick
# failure and feeds the retry/backoff path instead of wedging forever.
SUBPROCESS_TIMEOUT_SECONDS = int(os.environ.get("CODEBOT_SUBPROCESS_TIMEOUT", "120"))
# Cap the e2e-fails -> resume-to-fix -> re-run loop so a failure Claude can't resolve
# (e.g. an external resource stuck from a prior run) doesn't spin forever.
E2E_MAX_ROUNDS = int(os.environ.get("CODEBOT_E2E_MAX_ROUNDS", "5"))
QUALITY_GATE_MAX_ROUNDS = int(os.environ.get("CODEBOT_QUALITY_GATE_MAX_ROUNDS", "3"))
# After this many CONSECUTIVE failures of the same FSM state, codebot stops retrying
# silently and emails the user (entering WAIT_STUCK). Any successful tick resets it.
MAX_STATE_FAILURES = int(os.environ.get("CODEBOT_MAX_STATE_FAILURES", "5"))
# Cap the ask-question -> user-reply -> ask-again loop per phase; past this the task
# escalates to WAIT_STUCK instead of emailing yet another question.
QUESTION_MAX_ROUNDS = int(os.environ.get("CODEBOT_QUESTION_MAX_ROUNDS", "8"))
ARCHIVE_MAX_ROUNDS = int(os.environ.get("CODEBOT_ARCHIVE_MAX_ROUNDS", "3"))

# After opening a PR, codebot waits for the "Code Review" GitHub Action
# (OpenCodeReview) to finish and addresses its comments before notifying the user.
# Give up waiting for a single run after this long (the action itself caps at 30 min).
REVIEW_WAIT_TIMEOUT_SECONDS = int(os.environ.get("CODEBOT_REVIEW_WAIT_TIMEOUT", str(45 * 60)))
# Cap the fix<->re-review loop so a comment codebot can't resolve doesn't stall the PR.
REVIEW_MAX_ROUNDS = int(os.environ.get("CODEBOT_REVIEW_MAX_ROUNDS", "3"))

# While waiting on the user's merge decision, codebot also polls the PR for unresolved
# review conversation threads (e.g. a human reviewer's) and fixes them proactively. Cap
# that fix<->recheck loop so a thread codebot can't resolve doesn't stall the merge.
PR_THREAD_MAX_ROUNDS = int(os.environ.get("CODEBOT_PR_THREAD_MAX_ROUNDS", "3"))
# Cap consecutive merge-conflict resolution attempts on one PR (the base branch can keep
# moving while other PRs merge); past this the task escalates to WAIT_STUCK.
CONFLICT_MAX_ROUNDS = int(os.environ.get("CODEBOT_CONFLICT_MAX_ROUNDS", "3"))

# Gmail hard-caps messages around 25 MB; leave headroom for MIME overhead.
MAX_ATTACHMENT_BYTES = int(os.environ.get("CODEBOT_MAX_ATTACH_BYTES", str(22 * 1024 * 1024)))

# Project-specific runtime facts prepended to every agentic prompt (how to run the
# tests, what is NOT available in the container, ...). Either the env var or the file
# data/environment.md; the generic facts in prompts.ENVIRONMENT always apply.
def _environment_notes() -> str:
    inline = (os.environ.get("CODEBOT_ENVIRONMENT_NOTES") or "").strip()
    if inline:
        return inline
    try:
        return (DATA_DIR / "environment.md").read_text().strip()
    except OSError:
        return ""


ENVIRONMENT_NOTES = _environment_notes()

TOKEN_PATH = DATA_DIR / "token.json"
CREDENTIALS_PATH = DATA_DIR / "credentials.json"
STATE_PATH = DATA_DIR / "state.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Subjects carry the instance id so the user can tell instances' threads apart and
# address mailbox commands to one instance (a reply keeps the subject).
SUBJECT_PREFIX = f"[{INSTANCE_ID}]"
