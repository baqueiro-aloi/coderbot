#!/usr/bin/env bash
# Interactive setup: walks through every .env variable codebot needs, explains
# each one, offers discoverable defaults, validates what's cheaply checkable,
# and writes the result to .env. See README.md "One-time setup" for context.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_FILE=".env"
CREDENTIALS_PATH="data/credentials.json"
HAS_EXISTING_ENV="no"

echo "== codebot setup =="
echo "This walks through the values codebot needs and writes them to $ENV_FILE."

if [ -f "$ENV_FILE" ]; then
  HAS_EXISTING_ENV="yes"
  echo "Found an existing $ENV_FILE — its values will be offered as defaults."
fi

# existing_value VAR: VAR's value in the current .env, or "" if absent/no .env.
# A plain function (not an associative array) so this runs on bash 3.2, which
# macOS ships as /bin/bash and has no declare -A.
existing_value() {
  local var="$1" line
  [ "$HAS_EXISTING_ENV" = "yes" ] || return 0
  while IFS= read -r line; do
    case "$line" in
    "$var"=*) printf '%s' "${line#"$var"=}" ;;
    esac
  done <"$ENV_FILE"
}

# prompt_var VAR "explanation" "default" [secret: yes/no]
# Prints the explanation and prompt to stderr; prints the resolved value (and
# ONLY the resolved value) to stdout, so callers can do `x=$(prompt_var ...)`.
# For secret=yes, neither an existing/detected default nor the typed value is
# ever shown on the terminal.
prompt_var() {
  local var="$1" explanation="$2" default="$3" secret="${4:-no}"
  local current
  current="$(existing_value "$var")"
  local use_default="$default"
  [ -n "$current" ] && use_default="$current"

  echo >&2
  echo "$explanation" >&2
  local label="$var"
  if [ -n "$use_default" ]; then
    if [ "$secret" = "yes" ]; then
      label="$label [Enter to keep the current value]"
    else
      label="$label [$use_default]"
    fi
  fi

  local value
  if [ "$secret" = "yes" ]; then
    read -r -s -p "$label: " value
    echo >&2
  else
    read -r -p "$label: " value
  fi
  [ -z "$value" ] && value="$use_default"
  echo "$value"
}

# ---------------------------------------------------------------- required

while true; do
  CODEBOT_REPO_PATH=$(prompt_var "CODEBOT_REPO_PATH" \
    "Absolute path to the target project's git checkout that codebot will work on and open PRs against." \
    "")
  case "$CODEBOT_REPO_PATH" in
  /*) ;;
  *)
    echo "  -> must be an absolute path (starting with /)." >&2
    continue
    ;;
  esac
  if [ ! -e "$CODEBOT_REPO_PATH/.git" ]; then
    echo "  -> $CODEBOT_REPO_PATH is not a git checkout (no .git found there)." >&2
    continue
  fi
  break
done

while true; do
  raw=$(prompt_var "CODEBOT_DOC_ID" \
    "Google Doc id of the improvements backlog. Open the Doc and copy the id from its URL (.../document/d/<ID>/edit) — pasting the full URL also works." \
    "")
  if [[ "$raw" =~ /document/d/([a-zA-Z0-9_-]+) ]]; then
    CODEBOT_DOC_ID="${BASH_REMATCH[1]}"
  else
    CODEBOT_DOC_ID="$raw"
  fi
  if [[ -n "$CODEBOT_DOC_ID" && "$CODEBOT_DOC_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    break
  fi
  echo "  -> that doesn't look like a valid Doc id or URL." >&2
done

while true; do
  CODEBOT_USER_EMAIL=$(prompt_var "CODEBOT_USER_EMAIL" \
    "The email address codebot sends its updates to and reads your replies from." \
    "")
  if [[ "$CODEBOT_USER_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
    break
  fi
  echo "  -> that doesn't look like a valid email address." >&2
done

gh_token_default=""
gh_note="Create one at https://github.com/settings/tokens, or run: gh auth login"
if command -v gh >/dev/null 2>&1; then
  gh_token_default="$(gh auth token 2>/dev/null || true)"
  [ -n "$gh_token_default" ] && gh_note="Detected via the authenticated gh CLI — press Enter to use it."
fi
GH_TOKEN=$(prompt_var "GH_TOKEN" \
  "GitHub personal access token with 'repo' scope; used for git pushes over HTTPS and gh pr/api calls. $gh_note" \
  "$gh_token_default" "yes")

CLAUDE_CODE_OAUTH_TOKEN=$(prompt_var "CLAUDE_CODE_OAUTH_TOKEN" \
  "OAuth token for headless Claude Code runs inside the container (macOS keeps Claude credentials in the Keychain, which the Linux container can't read). Run 'claude setup-token' yourself — it opens a browser — then paste its output here." \
  "" "yes")

git_name_default="$(git config --global user.name 2>/dev/null || true)"
GIT_AUTHOR_NAME=$(prompt_var "GIT_AUTHOR_NAME" \
  "Git author name codebot commits as in the target repo." \
  "${git_name_default:-codebot}")

git_email_default="$(git config --global user.email 2>/dev/null || true)"
GIT_AUTHOR_EMAIL=$(prompt_var "GIT_AUTHOR_EMAIL" \
  "Git author email codebot commits as in the target repo." \
  "${git_email_default:-codebot@example.com}")

# ---------------------------------------------------------------- optional

repo_basename="$(basename "$CODEBOT_REPO_PATH")"
CODEBOT_PROJECT_NAME=$(prompt_var "CODEBOT_PROJECT_NAME" \
  "Optional: human-readable project name used in prompts. Leave blank to default to the repo directory name ($repo_basename)." \
  "")

CLAUDE_MODEL=$(prompt_var "CLAUDE_MODEL" \
  "Optional: Claude model codebot uses for its working sessions." \
  "claude-opus-4-8")

CODEBOT_LOG_LEVEL=$(prompt_var "CODEBOT_LOG_LEVEL" \
  "Optional: log verbosity — DEBUG traces every email, video, and git call; INFO is quieter." \
  "DEBUG")

# ---------------------------------------------------------------- Google OAuth

echo
if [ -f "$CREDENTIALS_PATH" ]; then
  echo "Found $CREDENTIALS_PATH."
  read -r -p "Run the Google OAuth consent flow now (python3 setup_oauth.py)? [y/N] " run_oauth
  if [[ "$run_oauth" =~ ^[Yy] ]]; then
    if ! python3 -c "import google_auth_oauthlib" >/dev/null 2>&1; then
      echo "Installing Python dependencies (pip install -r requirements.txt)..."
      pip install -r requirements.txt
    fi
    python3 setup_oauth.py
  else
    echo "Skipping for now — run 'python3 setup_oauth.py' yourself before starting codebot."
  fi
else
  cat <<MSG
$CREDENTIALS_PATH not found. Codebot needs a Google OAuth client (Desktop app)
to read/update the backlog Doc and send email:
  1. In Google Cloud Console, create a project (or use an existing one).
  2. Enable the Gmail, Google Docs, and Google Drive APIs.
  3. Create an OAuth client of type 'Desktop app'.
  4. Download its JSON and save it as $CREDENTIALS_PATH.
Then run 'python3 setup_oauth.py' to complete the consent flow (writes data/token.json).
MSG
fi

# ---------------------------------------------------------------- write .env

if [ -f "$ENV_FILE" ]; then
  backup="$ENV_FILE.bak.1"
  n=1
  while [ -e "$backup" ]; do
    n=$((n + 1))
    backup="$ENV_FILE.bak.$n"
  done
  echo
  read -r -p "$ENV_FILE already exists. Back it up to $backup and overwrite? [y/N] " confirm
  if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo "Aborted — $ENV_FILE was left unchanged."
    exit 1
  fi
  cp "$ENV_FILE" "$backup"
  echo "Backed up existing $ENV_FILE to $backup."
fi

cat >"$ENV_FILE" <<EOF
CODEBOT_REPO_PATH=$CODEBOT_REPO_PATH
CODEBOT_DOC_ID=$CODEBOT_DOC_ID
CODEBOT_PROJECT_NAME=$CODEBOT_PROJECT_NAME
GH_TOKEN=$GH_TOKEN
GIT_AUTHOR_NAME=$GIT_AUTHOR_NAME
GIT_AUTHOR_EMAIL=$GIT_AUTHOR_EMAIL
CLAUDE_CODE_OAUTH_TOKEN=$CLAUDE_CODE_OAUTH_TOKEN
CLAUDE_MODEL=$CLAUDE_MODEL
CODEBOT_USER_EMAIL=$CODEBOT_USER_EMAIL
CODEBOT_LOG_LEVEL=$CODEBOT_LOG_LEVEL
EOF
chmod 600 "$ENV_FILE"

echo
echo "Wrote $ENV_FILE with:"
for var in CODEBOT_REPO_PATH CODEBOT_DOC_ID CODEBOT_PROJECT_NAME GH_TOKEN GIT_AUTHOR_NAME \
  GIT_AUTHOR_EMAIL CLAUDE_CODE_OAUTH_TOKEN CLAUDE_MODEL CODEBOT_USER_EMAIL CODEBOT_LOG_LEVEL; do
  echo "  - $var"
done
echo
echo "Next: docker compose up -d --build"
