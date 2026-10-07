"""Durable feedback intake and validated investigation contracts."""
import time

import prompts
import handoffs


def receive(store, state, repo, message_id, text):
    return store.record("feedback", state, repo, message_id,
        {"text": text, "original_text": text, "received_at": time.time(), "phase": state.get("state"),
         "thread_id": state.get("thread_id"), "acknowledged": False})


def pending(store, state, repo):
    rows = store.list("feedback", store.task_identity(state, repo))
    return sorted([row for row in rows if row["status"] in ("pending", "investigating")],
                  key=lambda row: row["created"])


def validate(value):
    if value.get("action") not in ("answer", "correction", "replan", "question"):
        raise ValueError("Invalid feedback assessment action")
    for key in ("answer", "reason", "references"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"Feedback assessment requires {key}")
    return value


def investigation(state, row):
    return ("Investigate this authorized user feedback against actual approved OpenSpec "
        "proposal, design, specs and implementation. Read files and inspect code as needed. "
        "Do not edit code, commit, push or merge. Answer any factual question and preserve "
        "any requirement assertion even when phrased as a question. Classify material "
        "omissions, scope/architecture changes or invalidated assumptions as replan; "
        "localized unambiguous defects within approved intent as correction. Ask only "
        "a concrete unresolved product decision.\n" + handoffs.DECISION_INSTRUCTIONS + "\n"
        f"Task: {state.get('item')}\nChange: {state.get('slug')}\n"
        f"Archive: {state.get('archive_path')}\n"
        + prompts.fenced("user feedback", row["data"]["text"])
        + '\nReturn ONLY JSON: {"action":"answer|correction|replan|question",'
        '"answer":"factual answer or concrete question", "reason":"impact reasoning",'
        '"references":"actual inspected file/requirement references"}.')
