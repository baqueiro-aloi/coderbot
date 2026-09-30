"""Immutable, isolated baseline worktrees for regression attribution."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import re
import uuid

import operations
from checks import execute


@contextmanager
def worktree(repo, sha, data_dir):
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Baseline must use a full immutable base SHA")
    root = Path(data_dir) / "baselines"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    result = operations.run(["git", "worktree", "add", "--detach", str(path), sha], cwd=repo, timeout=120)
    if result.returncode:
        raise RuntimeError("Could not prepare baseline worktree: " + result.stderr[-500:])
    try:
        yield path
    finally:
        removed = operations.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, timeout=120)
        if removed.returncode:
            raise RuntimeError("Baseline cleanup failed: " + removed.stderr[-500:])
