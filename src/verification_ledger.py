"""Approved requirement inventory and scoped verification exceptions."""
import hashlib
import json
from pathlib import Path
import re


def requirements(repo, state):
    active = Path(repo) / f"openspec/changes/{state['slug']}"
    root = active if active.is_dir() else Path(repo) / state["archive_path"] if state.get("archive_path") else active
    result = []
    for path in sorted((root / "specs").rglob("*.md")):
        text = path.read_text()
        for match in re.finditer(r"^### Requirement:[ \t]*([^\n]+)\n(.*?)(?=^### Requirement:|\Z)", text, re.M | re.S):
            title = match.group(1).strip()
            result.append({"id": hashlib.sha256((str(path.relative_to(root)) + title).encode()).hexdigest(),
                           "title": title, "spec": str(path.relative_to(repo)),
                           "scenarios": re.findall(r"^#### Scenario:\s*(.+)$", match.group(2), re.M)})
    return result


def validate_coverage(inventory, report, snapshot):
    if report.get("snapshot") != snapshot:
        raise ValueError("Requirement coverage is stale")
    values = report.get("requirements", [])
    if not isinstance(values, list) or any(not isinstance(entry, dict) or not entry.get("id") for entry in values):
        raise ValueError("Invalid requirement coverage entries")
    if len({entry["id"] for entry in values}) != len(values):
        raise ValueError("Duplicate requirement coverage entries")
    entries = {entry["id"]: entry for entry in values}
    missing = []
    for requirement in inventory:
        entry = entries.get(requirement["id"], {})
        if entry.get("status") != "implemented" or not entry.get("implementation") or not entry.get("verification"):
            missing.append(requirement["title"])
    return missing


def waiver(state, text, scope, snapshot):
    value = {"instruction": text, "reason": text, "scope": scope, "snapshot": snapshot}
    if value not in state.setdefault("check_waivers", []):
        state["check_waivers"].append(value)
    return value


def report_details(state):
    return json.dumps({key: state.get(key) for key in ("quality_report",
        "internal_review_report", "final_check_report", "check_waivers", "validation_overrides",
        "integration_inventory", "reviewed_remote_sha")}, ensure_ascii=False, indent=2)
