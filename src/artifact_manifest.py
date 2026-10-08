"""Run-bound artifact provenance for Playwright, Newman and test diagnostics."""
import hashlib
import json
from pathlib import Path


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, *, run_id, snapshot, status, artifacts):
    entries = []
    for entry in artifacts:
        file = Path(entry["path"]).resolve()
        entries.append({**entry, "path": str(file), "hash": file_hash(file), "size": file.stat().st_size})
    value = {"version": 1, "run_id": run_id, "snapshot": snapshot, "status": status, "artifacts": entries}
    Path(path).write_text(json.dumps(value, ensure_ascii=False))
    return value


def load(path, *, snapshot=None, approved=True, artifact_root=None):
    path = Path(path).resolve()
    value = json.loads(path.read_text())
    if value.get("version") != 1 or not value.get("run_id"):
        raise ValueError("Invalid artifact manifest")
    if snapshot is not None and value.get("snapshot") != snapshot:
        raise ValueError("Artifact content does not match delivered snapshot")
    if approved and value.get("status") != "pass":
        return []
    valid = []
    if not isinstance(value.get('artifacts'), list):
        raise ValueError('Invalid artifact collection')
    root = Path(artifact_root).resolve() if artifact_root else None
    for entry in value['artifacts']:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
            raise ValueError('Invalid artifact entry')
        file = Path(entry['path']).resolve()
        if root is not None and not file.is_relative_to(root):
            continue
        if (file.is_file() and file.stat().st_size == entry.get('size') and file.stat().st_size
                and file_hash(file) == entry.get("hash")):
            valid.append(entry)
    return valid
