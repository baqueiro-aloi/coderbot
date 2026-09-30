"""Immutable, isolated baseline worktrees for regression attribution."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import re
import uuid

import operations
from checks import execute


def signature(error, roots=()):
    normalized = error.replace("\r\n", "\n").strip()
    for root in roots:
        normalized = normalized.replace(str(root), "<repo>")
    # Only duration and stack-frame line locations are volatile. Assertion values
    # and error messages remain exact; never strip arbitrary numbers or IDs.
    normalized = re.sub(r'(File "[^"]+", line )\d+', r'\1<line>', normalized)
    return normalized


def compare(feature, baseline, *, roots=()):
    if feature["status"] == "pass":
        return {"status": "pass", "preexisting": [], "regressions": []}
    if feature["status"] != "fail" or baseline["status"] not in ("pass", "fail"):
        return {"status": "indeterminate", "preexisting": [], "regressions": []}
    old = baseline.get("failures", {})
    preexisting, regressions = [], []
    for test, error in feature.get("failures", {}).items():
        target = preexisting if test in old and signature(error, roots) == signature(old[test], roots) else regressions
        target.append(test)
    return {"status": "fail" if regressions else "pass" if preexisting else "indeterminate",
            "preexisting": preexisting, "regressions": regressions}


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
