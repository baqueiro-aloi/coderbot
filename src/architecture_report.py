"""Evidence-backed, informational architecture decisions on the PR's committed diff."""
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import quote


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PR = re.compile(r"https://github\.com/([^/]+)/([^/]+)/pull/\d+\Z")
DIFF_MAX = 140_000
CONTEXT_MAX = 45_000


def _git(repo: Path, *args: str) -> str:
    run = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                         timeout=120, check=True)
    return run.stdout


def collect(repo: Path, base: str, archive: str) -> dict:
    """Build bounded input from committed changes, including actual archived design."""
    if not _SHA.fullmatch(base):
        raise ValueError("invalid task base commit")
    head = _git(repo, "rev-parse", "HEAD").strip()
    if not _SHA.fullmatch(head):
        raise ValueError("invalid PR head commit")
    paths = [p for p in _git(repo, "diff", "--name-only", "--diff-filter=ACMR",
                            f"{base}..{head}").splitlines() if p]
    patch = _git(repo, "diff", "--unified=1", f"{base}..{head}")
    archived = (repo / archive).resolve() if archive else None
    root = (repo / "openspec" / "changes" / "archive").resolve()
    planned = []
    if archived and archived.is_dir() and archived.parent == root:
        files = [archived / "proposal.md", archived / "design.md"]
        files += sorted((archived / "specs").rglob("spec.md")) if (archived / "specs").is_dir() else []
        for file in files:
            if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(archived):
                planned.append(f"## {file.relative_to(archived)}\n{file.read_text()}")
    if not planned:
        raise ValueError("archived OpenSpec design unavailable for architecture comparison")
    context = "\n".join(planned)
    return {"head": head, "paths": paths, "diff": patch[:DIFF_MAX],
            "complete": len(patch) <= DIFF_MAX and len(context) <= CONTEXT_MAX,
            "planned": context[:CONTEXT_MAX]}


def parse(text: str, paths: list[str]) -> list[dict]:
    """Fail on malformed analysis; discard unsupported or out-of-PR candidates."""
    obj = json.loads(text.strip())
    if not isinstance(obj, dict) or not isinstance(obj.get("decisions"), list):
        raise ValueError("architecture report must have a decisions list")
    allowed = set(paths)
    decisions = []
    rejected = Counter()
    for raw in obj["decisions"]:
        if not isinstance(raw, dict):
            rejected["item must be an object"] += 1
            continue
        title, impact = raw.get("title"), raw.get("impact")
        refs = raw.get("paths")
        errors = [reason for valid, reason in (
            (raw.get("kind") in ("decision", "assumption"),
             "kind must be decision or assumption"),
            (type(raw.get("planned")) is bool, "planned must be a JSON boolean"),
            (isinstance(title, str) and 5 <= len(title.strip()) <= 120,
             "title must contain 5-120 characters"),
            (isinstance(impact, str) and 5 <= len(impact.strip()) <= 300,
             "impact must contain 5-300 characters"),
            (isinstance(refs, list) and bool(refs) and
             all(isinstance(path, str) and path in allowed for path in refs),
             "paths must be a nonempty list of exact changed-file paths"),
        ) if not valid]
        if errors:
            rejected.update(errors)
            continue
        decisions.append({"kind": raw["kind"], "planned": raw["planned"],
                          "title": title.strip(), "impact": impact.strip(),
                          "paths": list(dict.fromkeys(refs))[:3]})
    if obj["decisions"] and not decisions:
        details = "; ".join(f"{reason} ({count} items)" for reason, count in rejected.items())
        raise ValueError("all architectural claims lacked valid changed-file evidence "
                         f"or schema: {details}")
    return decisions[:7]


def changed(previous: list[dict] | None, current: list[dict]) -> list[dict]:
    """Only material changes: title, impact, type or plan status for a file boundary."""
    if previous is None:
        return current
    known = {(item["kind"], item["planned"], item["title"], item["impact"],
              tuple(item["paths"])) for item in previous}
    added = [item for item in current if (item["kind"], item["planned"], item["title"],
                                          item["impact"], tuple(item["paths"])) not in known]
    current_paths = {path for item in current for path in item["paths"]}
    removed = [dict(item, kind="removed") for item in previous
               if not set(item["paths"]) & current_paths]
    return added + removed


def format_report(pr_url: str, head: str, items: list[dict], *, update: bool = False,
                  complete: bool = True) -> str:
    match = _PR.fullmatch(pr_url)
    if not match or not _SHA.fullmatch(head):
        raise ValueError("invalid PR URL or head SHA")
    lines = ["Architecture update (informational):" if update else
             "Architectural decisions and assumptions (informational):",
             f"PR: {pr_url}", "No action is needed to keep the automated review moving.", ""]
    if not items:
        lines.append("No additional significant architectural decisions were identified."
                     if complete else "Analysis was incomplete; no absence of decisions is claimed.")
    for n, item in enumerate(items, 1):
        label = ("Decision" if item["kind"] == "decision" else
                 "Removed decision/assumption" if item["kind"] == "removed" else
                 "Unverified assumption")
        planned = "in the approved design" if item["planned"] else "not specified in the approved design"
        lines.extend((f"{n}. {label}: {item['title']} ({planned})",
                      f"   Impact: {item['impact']}"))
        for path in item["paths"]:
            url = (f"{pr_url}/files" if item["kind"] == "removed" else
                   f"https://github.com/{match[1]}/{match[2]}/blob/{head}/{quote(path, safe='/')}")
            lines.append(f"   Evidence: {url}")
    if not complete:
        lines.append("Analysis coverage was limited by the size of the change.")
    return "\n".join(lines)
