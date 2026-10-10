"""Read-only Git state including index, exact filenames and operation markers."""
import hashlib
import json
from pathlib import Path
import subprocess


def _git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, timeout=60)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args,
                                            output=result.stdout, stderr=result.stderr)
    return result.stdout


def inspect(repo):
    repo = Path(repo)
    raw = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = iter(raw.decode("utf-8", errors="surrogateescape").split("\0"))
    files = {}
    for entry in entries:
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        original = next(entries) if "R" in status or "C" in status else None
        candidate = repo / path
        if candidate.is_symlink():
            content = str(candidate.readlink()).encode()
        elif candidate.is_file():
            content = candidate.read_bytes()
        else:
            content = b""
        files[path] = {"status": status, "original": original,
                       "hash": hashlib.sha256(content).hexdigest()}
    gitdir = Path(_git(repo, "rev-parse", "--absolute-git-dir").decode().strip())
    operations = [name for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD",
                  "rebase-merge", "rebase-apply") if (gitdir / name).exists()]
    value = {"head": _git(repo, "rev-parse", "HEAD").decode().strip(), "files": files,
             "index": hashlib.sha256(_git(repo, "diff", "--cached", "--binary")).hexdigest(),
             "operations": operations}
    value["fingerprint"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


def record(store, state, repo, *, initial=False):
    value = inspect(repo)
    identity = "task-start" if initial else value["fingerprint"]
    return store.record("provenance", state, repo, identity, value, status="complete")


def record_turn(store, state, repo, before, after):
    changes = {path: value for path, value in after["files"].items()
               if before["files"].get(path) != value}
    return store.record("provenance", state, repo, "turn-" + after["fingerprint"],
        {"kind": "turn", "before": before["fingerprint"], "after": after["fingerprint"],
         "files": changes}, status="complete")
