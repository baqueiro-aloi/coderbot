"""Explicit ownership of OpenSpec final-check tasks; no title heuristics."""
import re
from pathlib import Path

FINAL_CHECKS = "[codebot:final-checks]"
TASK = re.compile(r"^(\s*- \[)([ xX])(\]\s+)(.*)$", re.MULTILINE)


def inspect(repo, slug):
    path = Path(repo) / "openspec/changes" / slug / "tasks.md"
    tasks = list(TASK.finditer(path.read_text()))
    pending = [task for task in tasks if task[2] == " "]
    return {"total": len(tasks), "complete": len(tasks) - len(pending),
            "implementation": [task[4] for task in pending if FINAL_CHECKS not in task[4]],
            "final_checks": [task[4] for task in pending if FINAL_CHECKS in task[4]]}


def complete_final_checks(repo, slug):
    path = Path(repo) / "openspec/changes" / slug / "tasks.md"
    text = path.read_text()
    path.write_text(TASK.sub(lambda task: task[1] + "x" + task[3] + task[4]
        if task[2] == " " and FINAL_CHECKS in task[4] else task[0], text))
