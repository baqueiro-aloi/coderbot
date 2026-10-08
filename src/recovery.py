"""Recovery plans describe ownership and preserve ambiguous work by isolation."""
import json
from pathlib import Path
import subprocess
import shutil
import uuid

import repo_provenance


def begin(store, state, repo, reason, resume):
    current = repo_provenance.inspect(repo)
    row = store.record("recovery", state, repo, current["fingerprint"] + resume,
        {"origin": state["state"], "resume": resume, "reason": reason,
         "before": current, "attempts": 0})
    state["recovery_id"] = row["id"]
    state["state"] = "RECOVERING"
    return row


def ownership(store, state, repo, current):
    rows = store.list("provenance", store.task_identity(state, repo), identity="task-start")
    baseline = rows[0]["data"]["files"] if rows else None
    turns = [row["data"]["files"] for row in store.list("provenance", store.task_identity(state, repo))
             if row["data"].get("kind") == "turn"]
    owned = []
    protected = []
    for path in current["files"]:
        proven = any(files.get(path) == current["files"][path] for files in turns)
        (owned if baseline is not None and path not in baseline and proven else protected).append(path)
    return owned, protected


def attribution_prompt(state, current):
    return ("Read-only recovery attribution. Inspect task branch commits, task OpenSpec and "
        "available session/transcript evidence for the modified files below. Do not edit, "
        "commit, stash or discard anything. Attribute a path to this task ONLY with concrete "
        "evidence; leave ambiguous paths protected. Do not assume that a dirty worktree is "
        "task-owned. Return ONLY JSON with owned array and evidence object mapping each owned "
        "path to a concrete commit/transcript/spec reference.\n"
        + f"Task: {state.get('item')}\nBranch: {state.get('branch')}\n"
        + json.dumps(current["files"])
        + ("\nCurrent user-approved scope (do not repair excluded historical paths):\n"
           + state["verification_guidance"] if state.get("verification_guidance") else ""))


def validate_attribution(value, current):
    owned = value.get("owned")
    evidence = value.get("evidence")
    if not isinstance(owned, list) or not isinstance(evidence, dict):
        raise ValueError("Invalid ownership attribution")
    for path in owned:
        if not isinstance(path, str) or path not in current["files"] or not isinstance(evidence.get(path), str) or not evidence[path].strip():
            raise ValueError("Ownership attribution requires evidence for every path")
    return owned


def backup(repo, directory):
    """Durable private copy before isolation; original index/worktree untouched."""
    destination = Path(directory) / 'recovery-backups' / uuid.uuid4().hex
    destination.mkdir(mode=0o700, parents=True)
    before = repo_provenance.inspect(repo)
    for name in before['files']:
        source, target = Path(repo) / name, destination / 'files' / name
        if source.is_file() or source.is_symlink():
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
            if not target.is_symlink():
                target.chmod(0o600)
    for label, args in [('index.patch', ['diff', '--cached', '--binary']),
                        ('worktree.patch', ['diff', '--binary'])]:
        path = destination / label
        path.write_bytes(subprocess.run(['git', *args], cwd=repo, capture_output=True,
                                      check=True, timeout=60).stdout)
        path.chmod(0o600)
    after = repo_provenance.inspect(repo)
    generated = str(destination.relative_to(Path(repo))) + '/' if destination.is_relative_to(Path(repo)) else None
    actual = {name: value for name, value in after['files'].items()
              if generated is None or not name.startswith(generated)}
    if (before['files'] != actual or any(before[key] != after[key] for key in ('head', 'index', 'operations'))):
        raise ValueError('Concurrent edit during backup; original preserved, retry isolation')
    metadata = destination / 'metadata.json'
    metadata.write_text(json.dumps(before))
    metadata.chmod(0o600)
    return destination


def isolate(state, repo, directory, owned=()):
    """Keep the original checkout untouched; never check out its branch twice."""
    task = state["execution_task_id"][:16]
    destination = Path(directory) / "workspaces" / task
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        state['recovery_backup'] = str(backup(repo, directory))
        isolated_branch = "codebot-recovery-" + task
        subprocess.run(["git", "worktree", "add", "-b", isolated_branch, str(destination), "HEAD"],
            cwd=repo, capture_output=True, check=True, timeout=60)
        if owned:
            status = repo_provenance.inspect(repo)
            transferable = [name for name in owned if "U" not in status["files"][name]["status"]]
            patch = subprocess.run(["git", "diff", "HEAD", "--binary", "--", *transferable],
                cwd=repo, capture_output=True, check=True, timeout=60).stdout if transferable else b""
            if patch:
                subprocess.run(["git", "apply", "--binary", "-"], input=patch,
                    cwd=destination, capture_output=True, check=True, timeout=60)
            for name in owned:
                if status["files"][name]["status"] != "??":
                    continue
                source, target = Path(repo) / name, destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
        operations = repo_provenance.inspect(repo)["operations"]
        if operations:
            # Preserve the original operation; carry its merge intent into isolation.
            gitdir = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=repo,
                capture_output=True, check=True, text=True, timeout=60).stdout.strip()
            merge_head = Path(gitdir) / "MERGE_HEAD"
            if merge_head.is_file():
                state["isolated_merge_heads"] = merge_head.read_text().splitlines()
    isolated_branch = subprocess.run(["git", "branch", "--show-current"], cwd=destination,
        capture_output=True, check=True, text=True, timeout=60).stdout.strip()
    state.setdefault("remote_branch", state["branch"])
    state["branch"] = isolated_branch
    state.setdefault("original_workspace", str(repo))
    state["workspace_path"] = str(destination)
    return destination


def prompt(row, owned, state=None):
    state = state or {}
    return ("Recover this task-owned repository condition. You may repair application/test "
        "code and commit ONLY the listed task-owned paths, even though the original phase "
        "was archival. Inspect incomplete Git operations before starting new operations. "
        "Preserve both branch intents, unrelated edits and legitimate implementation. "
        "Verify repairs using focused checks and preserve required test repairs in commits. "
        "Do not push, merge a PR, discard unrelated files, or stash required repairs as the "
        "only copy. If a real product decision is needed ask a concrete question. If a "
        "material design change is needed report NEED_USER_INPUT for replanning.\n"
        + f"Condition: {row['data']['reason']}\nOwned paths: {json.dumps(owned)}\n"
        + "If Git is already clean, repair the stated original condition rather than "
        "declaring success from status alone. End with a short factual summary of repairs and commands verified."
        + ("\nCurrent user-approved scope (preserve excluded historical paths):\n"
           + state["verification_guidance"] if state.get("verification_guidance") else ""))
