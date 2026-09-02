#!/usr/bin/env bash
set -euo pipefail

: "${CODEBOT_REPO_PATH:?CODEBOT_REPO_PATH must be set in .env (absolute path of the target repo)}"
: "${GH_TOKEN:?GH_TOKEN must be set in .env (git/gh use it for HTTPS auth)}"

# Keep OpenCode credentials and resumable sessions in Codebot's bind-mounted data
# directory rather than sharing the host user's global OpenCode configuration.
export XDG_DATA_HOME=/app/data/opencode/data
export XDG_CONFIG_HOME=/app/data/opencode/config
export XDG_CACHE_HOME=/app/data/opencode/cache
export XDG_STATE_HOME=/app/data/opencode/state
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_STATE_HOME"
chown -R bot:bot /app/data/opencode

# Let the non-root user talk to the mounted docker socket.
if [ -S /var/run/docker.sock ]; then
  sock_gid="$(stat -c %g /var/run/docker.sock)"
  if [ "$sock_gid" = "0" ]; then
    # Socket owned by root group: adding bot to GID 0 would grant broad root-group
    # access. Re-group the socket to bot and grant only that group (not world) rw.
    echo "WARN: docker.sock is group root; re-grouping to bot with g+rw (not world)" >&2
    chgrp bot /var/run/docker.sock && chmod g+rw /var/run/docker.sock || true
  else
    getent group "$sock_gid" >/dev/null || groupadd -g "$sock_gid" docksock
    usermod -aG "$sock_gid" bot
  fi
fi

# Give claude a container-private ~/.claude.json instead of the live-shared host file
# (see docker-compose.yml). Seed it from the read-only host copy; fall back to an empty
# object if that copy is missing or itself corrupt, so claude always starts on valid JSON.
seed=/seed/.claude.json
local_cfg=/home/bot/.claude.json
valid_json() { python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$1" 2>/dev/null; }
if [ ! -s "$local_cfg" ] || ! valid_json "$local_cfg"; then
  if [ -s "$seed" ] && valid_json "$seed"; then
    cp "$seed" "$local_cfg" && echo "seeded $local_cfg from host copy" >&2
  else
    echo '{}' > "$local_cfg" && echo "WARN: no valid seed at $seed; initialized empty $local_cfg" >&2
  fi
fi
chown bot:bot "$local_cfg"

if [ "${CODEBOT_AGENT:-claude}" = "opencode" ]; then
  : "${OPENCODE_MODEL:?OPENCODE_MODEL must be provider/model when CODEBOT_AGENT=opencode}"
  command -v opencode >/dev/null || { echo "OpenCode is not installed in this image" >&2; exit 1; }
fi

exec setpriv --reuid=bot --regid=bot --init-groups env HOME=/home/bot bash -c '
  set -euo pipefail
  git config --global user.name "${GIT_AUTHOR_NAME:-codebot}"
  git config --global user.email "${GIT_AUTHOR_EMAIL:-codebot@localhost}"
  git config --global --add safe.directory "${CODEBOT_REPO_PATH}"
  # Git over HTTPS with GH_TOKEN (host SSH agent is not available in the container).
  gh auth setup-git
  # --replace-all (not a plain set): the key is multi-valued below, and a plain set fails
  # on an existing multi-valued key, which would break every restart of this container.
  git config --global --replace-all url."https://github.com/".insteadOf "git@github.com:"
  # The host may point origin at an SSH host alias from its own ~/.ssh/config, e.g.
  # "git@github-work:org/repo.git". The container has neither that config nor the key,
  # and gh refuses a remote whose host it does not recognize ("none of the git remotes
  # ... point to a known GitHub host"), so BOTH git and gh break. Map whatever alias
  # this checkout uses to HTTPS, exactly as a plain github.com remote is mapped.
  origin_url="$(git -C "${CODEBOT_REPO_PATH}" config --get remote.origin.url || true)"
  if [[ "$origin_url" =~ ^git@([^:]+): ]] && [ "${BASH_REMATCH[1]}" != "github.com" ]; then
    echo "origin uses SSH host alias ${BASH_REMATCH[1]}; rewriting it to https://github.com/" >&2
    git config --global --add url."https://github.com/".insteadOf "git@${BASH_REMATCH[1]}:"
  fi
  exec python3 -u /app/main.py
'
