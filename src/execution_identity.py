"""Content and environment identities, never a git-status approximation."""
import fnmatch
import hashlib
import json
from pathlib import Path
import subprocess


EXCLUDED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
                 "test-results", "playwright-report"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


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
