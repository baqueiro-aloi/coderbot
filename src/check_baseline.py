"""Immutable, isolated baseline worktrees for regression attribution."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import re
import uuid

import operations
from checks import execute
from execution_identity import digest, environment_identity, snapshot


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


def baseline_result(check, repo, sha, store):
    cache_task = "baseline:" + str(Path(repo).resolve()) + ":" + sha
    from checks import tool_versions
    environment = environment_identity(check.argv, repo, env_keys=check.env_keys, tools=tool_versions(check.argv, Path(repo) / check.cwd),
                                       key_path=store.path.parent / "identity.key")
    identity = digest({"sha": sha, "check": check.to_dict(), "environment": environment})
    saved = store.reusable_check(cache_task, identity)
    if saved and saved["data"]["result"]["status"] in ("pass", "fail"):
        return saved["data"]["result"]
    with worktree(repo, sha, store.path.parent) as path:
        # Absolute executables may be reused only with identical dependency inputs.
        dependency_inputs = ["requirements*.txt", "**/requirements*.txt", "package*.json", "**/package*.json"]
        if snapshot(repo, dependency_inputs) != snapshot(path, dependency_inputs):
            return {"status": "indeterminate", "failures": {}, "reason": "dependency_inputs_differ"}
        argv = [str(path / Path(arg).relative_to(Path(repo).resolve()))
                if arg.startswith(str(Path(repo).resolve()) + "/") and not ".venv/" in arg
                else arg for arg in check.argv]
        result = execute(replace(check, argv=argv), path, store, cache_task, reuse=False)
        result["failures"] = {test: signature(error, (path, repo)) for test, error in result.get("failures", {}).items()}
    store.record_check(cache_task, identity, result=result)
    return result


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
