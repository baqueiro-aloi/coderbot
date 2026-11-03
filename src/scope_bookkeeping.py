"""Controller-owned separation of append-only repair bookkeeping from approval."""
from pathlib import Path

import persistence
import proposal_package


def capture(state, root):
    if not state.get("approved_scope_fingerprint") or state.get("archive_path"):
        return None
    directory = Path(root) / "openspec/changes" / state["slug"]
    files = proposal_package.collect_directory(directory)
    return files if proposal_package.scope_fingerprint(files) == state["approved_scope_fingerprint"] else None


def finish(state, root, before):
    """Only appendices added during a repair turn are relocated, never intent edits.

    Existing task text, requirements/design and completion state remain untouched.
    This does not approve appended tasks or mark any verification gate passed.
    """
    if before is None or state.get("archive_path"):
        return False
    directory = Path(root) / "openspec/changes" / state["slug"]
    after = proposal_package.collect_directory(directory)
    old, new = proposal_package.scope_content(before), proposal_package.scope_content(after)
    if any(old.get(k) != new.get(k) for k in old.keys() | new.keys() if k != "tasks.md"):
        return False
    # Line-by-line prefix matching permits existing completion updates only.
    old_lines = old["tasks.md"].splitlines(keepends=True)
    new_lines = new["tasks.md"].splitlines(keepends=True)
    if new_lines[:len(old_lines)] != old_lines or len(new_lines) <= len(old_lines):
        return False
    actual = after["tasks.md"].splitlines(keepends=True)
    appendix = "".join(actual[len(old_lines):])
    log = directory / "execution-log.md"
    if log.is_symlink():
        raise ValueError("execution log must not be a symlink")
    previous = log.read_text() if log.exists() else ""
    persistence.atomic_write(log, previous + "\n## Controller-relocated repair appendix (not approved tasks)\n" + appendix)
    persistence.atomic_write(directory / "tasks.md", "".join(actual[:len(old_lines)]))
    return True
