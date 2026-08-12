"""Central configuration for codebot. Everything env-overridable."""
import os
from pathlib import Path

CODEBOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CODEBOT_DATA_DIR", CODEBOT_DIR / "data"))

# Backlog Google Doc. Required — set CODEBOT_DOC_ID in .env (validated in main()).
DOC_ID = os.environ.get("CODEBOT_DOC_ID", "")
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

# `or` (not a get-default) so an empty env value from .env still falls back,
# rather than passing --model "" to the claude CLI.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-4-8"

# DEBUG surfaces per-email/video/git detail in `docker compose logs`.
LOG_LEVEL = (os.environ.get("CODEBOT_LOG_LEVEL") or "DEBUG").upper()

POLL_INTERVAL_SECONDS = int(os.environ.get("CODEBOT_POLL_INTERVAL", "120"))
CLAUDE_TIMEOUT_SECONDS = int(os.environ.get("CODEBOT_CLAUDE_TIMEOUT", "7200"))
E2E_TIMEOUT_SECONDS = int(os.environ.get("CODEBOT_E2E_TIMEOUT", "3600"))

# After opening a PR, codebot waits for the "Code Review" GitHub Action
# (OpenCodeReview) to finish and addresses its comments before notifying the user.
# Give up waiting for a single run after this long (the action itself caps at 30 min).
REVIEW_WAIT_TIMEOUT_SECONDS = int(os.environ.get("CODEBOT_REVIEW_WAIT_TIMEOUT", str(45 * 60)))
# Cap the fix<->re-review loop so a comment codebot can't resolve doesn't stall the PR.
REVIEW_MAX_ROUNDS = int(os.environ.get("CODEBOT_REVIEW_MAX_ROUNDS", "3"))

# Gmail hard-caps messages around 25 MB; leave headroom for MIME overhead.
MAX_ATTACHMENT_BYTES = int(os.environ.get("CODEBOT_MAX_ATTACH_BYTES", str(22 * 1024 * 1024)))

TOKEN_PATH = DATA_DIR / "token.json"
CREDENTIALS_PATH = DATA_DIR / "credentials.json"
STATE_PATH = DATA_DIR / "state.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
]

SUBJECT_PREFIX = "[codebot]"
