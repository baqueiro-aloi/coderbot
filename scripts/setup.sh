#!/bin/sh
# Portable launcher: also works as `bash scripts/setup.sh` and `zsh scripts/setup.sh`.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
exec python3 -m scripts.setup "$@"
