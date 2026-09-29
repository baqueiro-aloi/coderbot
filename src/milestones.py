"""Static lifecycle progress images and per-task announcement bookkeeping."""
from pathlib import Path

STAGES = ("exploring", "proposing", "approval", "implementing", "verifying",
          "archiving", "pr_review", "merged")
LABELS = ("Exploration", "Proposal", "Awaiting approval", "Implementation",
          "Verification", "Archiving", "PR ready for review", "PR merged")
ASSETS = Path(__file__).resolve().parent / "assets" / "milestones"


def image(stage: str) -> Path:
    if stage not in STAGES:
        raise ValueError(f"unknown milestone: {stage}")
    return ASSETS / f"{stage}.png"


def label(stage: str) -> str:
    return LABELS[STAGES.index(stage)]


def announced(state: dict, stage: str) -> bool:
    return stage in state.get("milestones_announced", [])


def mark(state: dict, stage: str) -> None:
    if not announced(state, stage):
        state.setdefault("milestones_announced", []).append(stage)
