"""Explicit ownership of OpenSpec final-check tasks; no title heuristics."""
import re
from pathlib import Path

FINAL_CHECKS = "[codebot:final-checks]"
TASK = re.compile(r"^(\s*- \[)([ xX])(\]\s+)(.*)$", re.MULTILINE)


def inspect(repo, slug):
    path = Path(repo) / "openspec/changes" / slug / "tasks.md"
    tasks = list(TASK.finditer(path.read_text()))
    pending = [task for task in tasks if task[2] == " "]
    if not tasks:
        raise ValueError("OpenSpec tasks.md contains no tasks")
    return {"total": len(tasks), "complete": len(tasks) - len(pending),
            "implementation": [task[4] for task in pending if FINAL_CHECKS not in task[4]],
            "final_checks": [task[4] for task in pending if FINAL_CHECKS in task[4]]}


def validate_progress(repo, slug, instructions):
    """Cross-check the CLI's counts against the actual checklist."""
    actual = inspect(repo, slug)
    progress = instructions.get("progress") if isinstance(instructions, dict) else None
    if not isinstance(progress, dict):
        raise ValueError("OpenSpec apply progress is missing")
    expected = {"total": actual["total"], "complete": actual["complete"],
                "remaining": actual["total"] - actual["complete"]}
    if any(type(progress.get(key)) is not int or progress[key] != value
           for key, value in expected.items()):
        raise ValueError("OpenSpec apply counts do not match tasks.md")
    expected_state = "all_done" if expected["remaining"] == 0 else "ready"
    if instructions.get("state") != expected_state:
        raise ValueError("OpenSpec apply state does not match checklist progress")
    return actual


def complete_final_checks(repo, slug):
    path = Path(repo) / "openspec/changes" / slug / "tasks.md"
    text = path.read_text()
    path.write_text(TASK.sub(lambda task: task[1] + "x" + task[3] + task[4]
        if task[2] == " " and FINAL_CHECKS in task[4] else task[0], text))
