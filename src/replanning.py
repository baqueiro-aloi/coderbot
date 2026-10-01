"""Versioned complementary planning context preserves the original delivery."""
import hashlib

import prompts


def begin(state, row):
    previous = state.get("replan")
    state["replan"] = {"origin": state["state"], "feedback_id": row["id"],
        "original_slug": state.get("slug"), "original_archive": state.get("archive_path"),
        "original_pr": state.get("pr_url"), "feedback": row["data"]["text"],
        "assessment": row["data"].get("assessment", {})}
    if previous:
        state["replan"]["previous_revision"] = previous
    state.pop("approved_proposal", None)
    state.pop("reviewed_pr_snapshot", None)
    state.pop("pending_question", None)
    state.pop("return_state", None)
    state["state"] = "REPLANNING"


def prompt(state, repo):
    context = state["replan"]
    archived = context.get("original_archive")
    if archived:
        suffix = hashlib.sha256(context["feedback_id"].encode()).hexdigest()[:8]
        slug = context["original_slug"][:80] + "-revision-" + suffix
        state["slug"] = slug
        planning = f"Scaffold complementary change {slug} via openspec new change if absent. "
        planning += f"Link it to historical archive {archived}; do not rewrite that archive. "
    else:
        planning = f"Revise active change {state['slug']}. "
    return ("Revise planning only; preserve all legitimate implementation, index and Git history. "
        "Do not implement application code, discard changes, push or merge. " + planning
        + "Update proposal, design, specs and tasks coherently; retain implemented work and "
        "identify remaining work and changed verification/demo. Validate strictly. "
        "The user must approve this revised version before implementation resumes.\n"
        + prompts.fenced("user feedback", context["feedback"])
        + f"\nAssessment: {context.get('assessment')}\n"
        + "End with a short factual summary of revised requirements and retained work.")


def approve(state, fingerprint):
    state["approved_proposal"] = fingerprint
    if state.get("replan"):
        state.pop("archive_path", None)
        state.pop("proposal_sent_key", None)
        for key in ("quality_report", "internal_review_report", "final_check_report",
                    "reviewed_snapshot", "e2e_passed", "coverage_report"):
            state.pop(key, None)
    state["state"] = "IMPLEMENTING"
