#!/bin/bash
# Runs from the coderbot checkout on the volume, on every boot after bootstrap.sh (and
# again by `deploy.sh update`). Idempotent: seeds what is missing, rewrites the per-agent
# env, installs the systemd units and (re)starts the container.
set +x
set -euo pipefail
. /etc/coderbot/agent.conf
export AWS_DEFAULT_REGION="$REGION"
MNT=/mnt/coderbot
HERE="$MNT/coderbot/deploy/aws"
BOT_UID=501   # the container's `bot` user (see Dockerfile)

get_secret() { aws secretsmanager get-secret-value --secret-id "$SECRET_PREFIX/$1" --query SecretString --output text; }
# Credential files are seeded once: the app refreshes token.json / .credentials.json in
# place, so a boot must not overwrite them with the (older) copies in Secrets Manager.
seed() {  # seed <secret-name> <path>
  if [ "$RESEED_SECRETS" = "true" ] || [ ! -s "$2" ]; then
    mkdir -p "$(dirname "$2")"; get_secret "$1" > "$2"; chmod 600 "$2"
  fi
}

umask 077
mkdir -p "$MNT/data" "$MNT/claude" "$MNT/repo"
seed env                "$MNT/codebot.env"
seed claude-credentials "$MNT/claude/.credentials.json"
seed claude-json        "$MNT/claude.json" || echo '{}' > "$MNT/claude.json"

# The target repo checkout (the agent's working copy; uncommitted work lives here).
TARGET_DIR="$MNT/repo/$(basename "$TARGET_REPO")"
if [ ! -d "$TARGET_DIR/.git" ]; then
  export GH_TOKEN="$(grep -E '^GH_TOKEN=' "$MNT/codebot.env" | head -n1 | cut -d= -f2-)"
  askpass=$(mktemp "$MNT/codebot-askpass.XXXXXX")
  trap 'rm -f -- "$askpass"' EXIT
  cat > "$askpass" <<'ASKPASS'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' x-access-token ;;
  *Password*) printf '%s\n' "$GH_TOKEN" ;;
  *) exit 1 ;;
esac
ASKPASS
  chmod 700 "$askpass"
  GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone "https://github.com/$TARGET_REPO.git" "$TARGET_DIR"
  rm -f -- "$askpass"
  trap - EXIT
  unset GH_TOKEN
  # The container authenticates with gh; keep the token out of the remote URL.
  git -C "$TARGET_DIR" remote set-url origin "https://github.com/$TARGET_REPO.git"
fi

# Per-agent overrides, last in the compose env_file list so they win over codebot.env.
cat > "$MNT/agent.env" <<EOA
CODEBOT_INSTANCE=$AGENT_NAME
CODEBOT_REPO_PATH=$TARGET_DIR
EOA
# Per-agent secrets on the EBS volume are retained between boots and appended
# AFTER shared values so two Slack instances never reuse one app/token pair.
if [ -s "$MNT/agent.local.env" ]; then
  chmod 600 "$MNT/agent.local.env"
  cat "$MNT/agent.local.env" >> "$MNT/agent.env"
fi
# Last occurrence in the combined env wins, including per-agent overrides.
setting() { grep -h "^$1=" "$MNT/codebot.env" "$MNT/agent.env" | tail -n1 | cut -d= -f2-; }
source=$(setting CODEBOT_TASK_SOURCE)
channel=$(setting CODEBOT_COMM_CHANNEL)
upload=$(setting CODEBOT_EVIDENCE_UPLOAD)
if [ "${channel:-email}" = slack ]; then
  for setting in CODEBOT_SLACK_BOT_TOKEN CODEBOT_SLACK_APP_TOKEN; do
    if [ ! -s "$MNT/agent.local.env" ] || ! grep -Eq "^${setting}=.+" "$MNT/agent.local.env"; then
      echo "Slack mode requires $setting in $MNT/agent.local.env (unique per agent)" >&2
      exit 1
    fi
  done
fi
chmod 600 "$MNT/agent.env"

# Shared Google secrets may be placeholders in Jira+Slack without Drive. Check
# the effective per-agent settings, not just the shared .env, before seeding.
if [ "${source:-gdoc}" = gdoc ] || [ "${channel:-email}" = email ] || \
   ! [[ "$upload" =~ ^(off|false|0|no)$ ]]; then
  seed google-token       "$MNT/data/token.json"
  seed google-credentials "$MNT/data/credentials.json"
fi

chown -R "$BOT_UID" "$MNT/data" "$MNT/claude" "$MNT/repo" "$MNT/coderbot"
chown "$BOT_UID" "$MNT/codebot.env" "$MNT/agent.env" "$MNT/claude.json"

install -m 0755 "$HERE/instance/spot-watch.sh" /usr/local/sbin/coderbot-spot-watch
install -m 0644 "$HERE/instance/coderbot.service" "$HERE/instance/coderbot-spot-watch.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now coderbot-spot-watch
systemctl enable coderbot
# `up --build` is a no-op when the image cache on the volume is current.
systemctl restart coderbot
