#!/bin/bash
# Runs from the coderbot checkout on the volume, on every boot after bootstrap.sh (and
# again by `deploy.sh update`). Idempotent: seeds what is missing, rewrites the per-agent
# env, installs the systemd units and (re)starts the container.
set -euxo pipefail
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
seed google-token       "$MNT/data/token.json"
seed google-credentials "$MNT/data/credentials.json"
seed claude-json        "$MNT/claude.json" || echo '{}' > "$MNT/claude.json"

# The target repo checkout (the agent's working copy; uncommitted work lives here).
TARGET_DIR="$MNT/repo/$(basename "$TARGET_REPO")"
if [ ! -d "$TARGET_DIR/.git" ]; then
  GH_TOKEN="$(grep -E '^GH_TOKEN=' "$MNT/codebot.env" | head -n1 | cut -d= -f2-)"
  git clone "https://x-access-token:$GH_TOKEN@github.com/$TARGET_REPO.git" "$TARGET_DIR"
  # The container authenticates with gh; keep the token out of the remote URL.
  git -C "$TARGET_DIR" remote set-url origin "https://github.com/$TARGET_REPO.git"
fi

# Per-agent overrides, last in the compose env_file list so they win over codebot.env.
cat > "$MNT/agent.env" <<EOA
CODEBOT_INSTANCE=$AGENT_NAME
CODEBOT_REPO_PATH=$TARGET_DIR
EOA

chown -R "$BOT_UID" "$MNT/data" "$MNT/claude" "$MNT/repo" "$MNT/coderbot"
chown "$BOT_UID" "$MNT/codebot.env" "$MNT/agent.env" "$MNT/claude.json"

install -m 0755 "$HERE/instance/spot-watch.sh" /usr/local/sbin/coderbot-spot-watch
install -m 0644 "$HERE/instance/coderbot.service" "$HERE/instance/coderbot-spot-watch.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now coderbot-spot-watch
systemctl enable coderbot
# `up --build` is a no-op when the image cache on the volume is current.
systemctl restart coderbot
