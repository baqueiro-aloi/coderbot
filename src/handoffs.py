"""Concise, channel-neutral headings for messages requiring a human decision."""


def decision_card(state: dict, phase: str) -> str:
    name = phase.lower()
    if name in ("proposal for review", "revised proposal"):
        return "Your decision: approve the attached proposal to start implementation, or reply with requested changes."
    if name.startswith("question during"):
        return "Your input: answer the question below. I'll resume the current work once you reply."
    if name == "pr ready for review":
        return "Your decision: review the PR, then reply with changes or an explicit 'merge'."
    if "stuck" in name or name.startswith("merge failed"):
        return "Your input: review the problem below and reply with guidance or 'retry' when ready."
    if name == "clarification needed":
        stage = state.get("state")
        if stage == "WAIT_APPROVAL":
            return "Your decision: explicitly approve the proposal or describe the changes you want."
        if stage == "WAIT_MERGE":
            return "Your decision: request PR changes or explicitly tell me to merge."
        return "Your input: clarify what you would like me to do next."
    return ""


def verification(state: dict) -> str:
    gate = state.get("quality_report") or {}
    review = state.get("internal_review_report") or {}
    lines = ["Verification:"]
    lines.append("- OpenSpec: passed" if gate.get("openspec") == "pass"
                 else "- OpenSpec: outcome unavailable")
    checks = gate.get("commands") or []
    lines.append("- Checks: " + ("; ".join(checks) if checks else "outcome unavailable"))
    final = state.get("final_check_report") or {}
    for check in final.get("checks", []):
        result = check.get("gate", {}).get("status", check.get("status", "unavailable"))
        lines.append(f"- Final {check.get('check', 'check')}: {result}")
        if check.get("gate", {}).get("preexisting"):
            lines.append("  Pre-existing: " + "; ".join(check["gate"]["preexisting"]))
        if check.get("status") in ("unknown", "infrastructure"):
            lines.append("  Outcome not established; not reported as passed.")
    if gate.get("preexisting"):
        lines.append("- Confirmed pre-existing failures: " + "; ".join(gate["preexisting"]))
    lines.append("- Internal review: passed" if review.get("status") == "pass"
                 else "- Internal review: outcome unavailable")
    if not state.get("has_e2e_harness"):
        lines.append("- E2E: not applicable (no harness)")
    else:
        lines.append("- E2E: " + ("passed" if state.get("e2e_passed") is True
                                     else "outcome unavailable"))
    return "\n".join(lines)


def evidence_index(files, url: str | None) -> str:
    items = []
    if url:
        items.append(f"- Demo video (feature walkthrough): {url}")
    for file in files:
        suffix = file.suffix.lower()
        description = ("API run report" if suffix == ".html" else
                       "Feature recording" if suffix in (".mp4", ".webm") else
                       "Supporting screenshot" if suffix in (".png", ".jpg", ".jpeg") else
                       "Supporting evidence")
        items.append(f"- {description}: attached {file.name}")
    return "Evidence:\n" + ("\n".join(items) if items else "- No artifact available.")
