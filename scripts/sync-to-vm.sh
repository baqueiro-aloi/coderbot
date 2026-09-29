#!/usr/bin/env bash
# One-time copy. Stop the bot on both machines; its state and checkout must be stable.
set -euo pipefail

usage='Usage: bash scripts/sync-to-vm.sh user@host'
if [[ $# -eq 1 && $1 == --help ]]; then
  echo "$usage"
  echo 'Copies Coderbot to ~/codebot/app and CODEBOT_REPO_PATH to ~/codebot/target.'
  exit 0
fi
if [[ $# -ne 1 || ! $1 =~ ^[[:alnum:]_.-]+@[[:alnum:].-]+$ ]]; then
  echo "$usage" >&2
  exit 2
fi
remote=$1

for tool in rsync ssh python3 git; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
if [[ ! -f $HOME/.npmrc ]]; then
  echo "Missing $HOME/.npmrc; the Docker Compose override requires this registry configuration" >&2
  exit 1
fi

root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ ! -f $root/.env ]]; then
  echo "Missing $root/.env; configure the target repo with scripts/setup.sh first" >&2
  exit 1
fi
if [[ -e $root/.env.local ]]; then
  echo "Existing $root/.env.local would be copied over the VM backup; move it aside first" >&2
  exit 1
fi

# Never source .env: it is configuration, not executable shell code.
target=$(cd "$root" && python3 - "$root/.env" <<'PY'
import sys
from scripts.setup_env import EnvFile
print(EnvFile(sys.argv[1]).values.get("CODEBOT_REPO_PATH", ""))
PY
)
if [[ $target != /* || ! -d $target ]] || ! git -C "$target" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo 'CODEBOT_REPO_PATH must point to an existing local Git checkout' >&2
  exit 1
fi
if [[ $target == "$root" || $target == "$root/"* ]]; then
  echo 'CODEBOT_REPO_PATH must be outside the Coderbot checkout' >&2
  exit 1
fi

# The VM owns its own paths. Generate a private, short-lived .env copy locally,
# preserving all other values and comments, and keep the Mac's .env unchanged.
vm_home=$(ssh -o BatchMode=yes "$remote" 'printf %s "$HOME"')
if [[ $vm_home != /* || $vm_home == *$'\n'* ]]; then
  echo 'Could not determine the VM home directory over SSH' >&2
  exit 1
fi
ssh -o BatchMode=yes "$remote" \
  'if [ -e "$HOME/codebot/app/.env.local" ]; then echo "VM .env.local already exists; move it aside before a new one-time copy" >&2; exit 1; fi'
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
umask 077
( cd "$root" && python3 -m scripts.prepare_vm_env "$root/.env" "$tmp/.env" \
    "$root" "$target" "$vm_home/codebot/target" )

ssh -o BatchMode=yes "$remote" 'mkdir -p "$HOME/codebot/app" "$HOME/codebot/target"'
# Source and credentials come across; native dependencies and browser downloads
# from macOS/arm64 must be installed again on Linux/amd64. Do not delete any VM
# dependencies that may already have been installed there.
excludes=(--exclude='node_modules/' --exclude='.venv/' --exclude='venv/'
          --exclude='ms-playwright/')
rsync -az "${excludes[@]}" --exclude='/data/heartbeat' -- "$root/" "$remote:~/codebot/app/"
rsync -az "${excludes[@]}" -- "$target/" "$remote:~/codebot/target/"

# Keep the original Mac settings beside the VM-adjusted file. If a local
# .env.local existed, it was also copied by rsync; replace the VM copy with
# the .env that was just transferred, never modify the local .env.local.
ssh -o BatchMode=yes "$remote" 'cp -p "$HOME/codebot/app/.env" "$HOME/codebot/app/.env.local"'
rsync -a -- "$tmp/.env" "$remote:~/codebot/app/.env"
ssh -o BatchMode=yes "$remote" \
  'if [ -f "$HOME/.npmrc" ] && [ ! -e "$HOME/.npmrc.before-codebot" ]; then cp -p "$HOME/.npmrc" "$HOME/.npmrc.before-codebot"; chmod 600 "$HOME/.npmrc.before-codebot"; fi'
rsync -a -- "$HOME/.npmrc" "$remote:~/.npmrc"
ssh -o BatchMode=yes "$remote" 'chmod 600 "$HOME/.npmrc"'

# rsync preserves private data/ and Git permissions but creates VM files as the
# SSH user. The container drops to uid/gid 501 before config imports and writes
# instance_fingerprint, state.json and branches. Give those two mounted trees
# to that user; do not chown all of app/, since Compose still reads its .env.
if ! ssh -o BatchMode=yes "$remote" \
    'mkdir -p "$HOME/codebot/app/data" && sudo -n chown -R 501:501 "$HOME/codebot/app/data" "$HOME/codebot/target"'; then
  echo 'Cannot set VM ownership. Run: sudo chown -R 501:501 ~/codebot/app/data ~/codebot/target' >&2
  exit 1
fi

echo "Copied both repos to $remote:~/codebot/{app,target}."
echo "On the VM, ~/codebot/app/.env.local has the original paths and .env uses $vm_home/codebot/target."
echo 'Copied ~/.npmrc with mode 600; the container copies it into its bot home on startup.'
echo 'Set data/ and target checkout ownership to uid/gid 501 for the container bot.'
echo 'The container initializes its heartbeat on startup; copied Mac heartbeat is excluded.'
echo 'Install target dependencies and Playwright Chromium for Linux/amd64 inside the VM/container.'
echo 'If Mac-built node_modules were copied previously, remove those stale directories on the VM first.'
