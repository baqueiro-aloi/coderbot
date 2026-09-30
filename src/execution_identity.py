"""Content and environment identities, never a git-status approximation."""
import fnmatch
import hashlib
import json
import hmac
import os
from pathlib import Path
import subprocess


EXCLUDED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
                 "test-results", "playwright-report"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def environment_identity(argv, cwd, *, env_keys=(), environ=None, tools=None, key_path):
    """Use a private local HMAC key: secret values never become stored metadata."""
    key_path = Path(key_path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as output:
            output.write(os.urandom(32))
    key = key_path.read_bytes()
    env = os.environ if environ is None else environ
    private = hmac.new(key, json.dumps({name: env.get(name) for name in sorted(env_keys)},
                       sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return digest({"argv": list(argv), "cwd": str(Path(cwd).resolve()),
                   "environment": private, "tools": tools or {}})


def snapshot(repo, inputs=None):
    repo = Path(repo).resolve()
    files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo, capture_output=True, timeout=30, check=True).stdout.decode().split("\0")
    selected = []
    patterns = inputs or ["*"]
    for name in sorted(set(files) - {""}):
        path = Path(name)
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.name == ".env" or path.name.startswith(".env.") and not path.name.endswith("example"):
            continue
        if not any(fnmatch.fnmatch(name, p) or name == p or name.startswith(p.rstrip("/") + "/")
                   for p in patterns):
            continue
        full = repo / name
        if full.is_symlink():
            # Link identity is relevant; never follow links into external secret/caches.
            selected.append((name, "link", str(full.readlink())))
        elif full.is_file():
            selected.append((name, full.stat().st_mode & 0o111, hashlib.sha256(full.read_bytes()).hexdigest()))
        else:
            selected.append((name, "missing"))
    return digest(selected)
