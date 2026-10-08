"""Concise, channel-neutral headings for messages requiring a human decision."""
import re


DECISION_INSTRUCTIONS = """
Whenever a human decision is genuinely required, ask it as a concrete action:
"Do you authorize ...?", not just "verification blocked" or "give guidance".
For one authorization, offer exactly "1. Yes — <action and consequence>" and
"2. No — keep the current work paused, without aborting or marking it complete".
For alternatives, offer 3-4 numbered, mutually distinct feasible options with a
short consequence for each. Mark one "(Recommended)" when justified; never recommend
waiving checks, discarding work or merging over unresolved findings by default.
Tell the user to reply Yes/No for a binary decision, or the option number and any
required details for alternatives. Always allow a full-text answer, including
"3. <explanation>" or an alternative not listed. Interpret the entire answer;
qualifications and requested changes override a leading option number. Put the full
question and choices in readable prose, not only an attachment. Use NEED_USER_INPUT: in working-session responses;
in a JSON-only utility contract, put the prose in the required question/answer field
instead, and never emit a sentinel outside that JSON contract. An option that
needs missing data must explicitly request it, never invent it. Ask only for a real
human decision, not permission to run already authorized tools. These rules apply
in every phase and in both email and Slack. A choice grants only the named action;
never infer new scope, whole-task completion, push or merge beyond that action.
Ask exactly one decision per turn, then stop and wait for its answer. Put each
numbered option on its own line. Do not repeat the question or offer a second,
generic menu such as answer/explain/wait. Keep background context separate from
the single actionable question.
"""


def _option(label, reply, *, wait=False, details=False):
    return {"label": label, "reply": reply, "wait": wait, "details": details}


def _question_parts(question):
    """Parse a consecutive option list, including legacy inline agent output."""
    markers = list(re.finditer(r"(?<!\S)([1-4])[.)]\s+", question))
    if not 2 <= len(markers) <= 4 or [int(m[1]) for m in markers] != list(range(1, len(markers) + 1)):
        return question.strip(), []
    labels = [" ".join(question[m.end():markers[i + 1].start() if i + 1 < len(markers) else len(question)].split())
              for i, m in enumerate(markers)]
    if not all(labels):
        return question.strip(), []
    return question[:markers[0].start()].strip(), labels


def without_question(body, question):
    """Remove repeated copies of this question only, preserving other context."""
    pattern = r"\s+".join(re.escape(word) for word in question.split())
    return re.sub(pattern, "", body).strip() if pattern else body


def decision(state, phase, question=None):
    """Controller choices use existing FSM operations, never invent new commands."""
    name = phase.lower()
    if question and not name.startswith("question during "):
        # A concrete supplied question is the decision, not a prompt to add a
        # second controller menu based on the notification's subject.
        return decision(state, "question during " + str(state.get("state", "")), question)
    stage = state.get("state")
    target, binary = "WAIT_REPLY", False
    no = _option("No — preserve the work and keep waiting", "", wait=True)
    if name == "verification blocked":
        kind = state.get("verification_blocker", {}).get("kind")
        if kind == "unfinished or unclassified tasks":
            title = "Do you authorize continuing the pending implementation of the already approved spec?"
            options = [_option("Yes — finish only the approved pending tasks, then verify (Recommended)",
                "I explicitly authorize completing the pending implementation tasks of the already "
                "approved spec. Preserve existing work and history; do not replan or expand scope. "
                "Then verify and reconcile current evidence."), no]
            binary = True
        elif kind == "approval":
            title = "How should we resolve the pending approval?"
            options = [_option("Provide the specific approval or decision requested below (Recommended)",
                               "My decision on the pending approval is:", details=True),
                       _option("Clarify what approval is missing", "Explain the exact pending approval and its consequences."),
                       _option("Keep waiting without changing the work", "", wait=True)]
        elif kind == "scope drift":
            title = "How should we reconcile the changed task scope?"
            options = [_option("Reconcile the checklist with the approved scope; specify corrections (Recommended)",
                               "Reconcile the checklist with the approved scope using these corrections:", details=True),
                       _option("Request a scope revision; describe it for review", "Prepare a scope revision for review, not implementation:", details=True),
                       _option("Keep waiting without changing scope", "", wait=True)]
        else:
            title = "How should we resolve the missing evidence or execution prerequisite?"
            options = [_option("Provide the missing evidence or recovery guidance below (Recommended)",
                               "Use this evidence or recovery guidance, without crediting unverified results:", details=True),
                       _option("Clarify exactly which result or prerequisite is missing",
                               "Explain exactly which evidence, result or prerequisite is missing and why."),
                       _option("Keep waiting; do not waive checks", "", wait=True)]
    elif name in ("proposal for review", "revised proposal") or (name == "clarification needed" and stage == "WAIT_APPROVAL"):
        target = "WAIT_APPROVAL"
        title = "Do you authorize implementing the attached proposal?"
        options = [_option("Yes — approve this proposal and start implementation", "approve"), no]
        binary = True
    elif name in ("pr ready for review", "pr updated") or name.startswith("merge blocked") or name.startswith("merge failed") or name == "unresolved review threads need your help" or (name == "clarification needed" and stage == "WAIT_MERGE"):
        target = "WAIT_MERGE"
        title = "What should I do with this PR?"
        options = [_option("Request changes; describe them", "Requested PR changes:", details=True),
                   _option("Authorize 'merge' after reviewing this PR; existing gates still apply", "merge"),
                   _option("Keep waiting without merging (Recommended)", "", wait=True)]
        if name in ("merge blocked — unresolved review comments", "merge blocked — could not verify review comments", "unresolved review threads need your help"):
            options.append(_option("Explicitly authorize 'merge anyway'; bypass the review-thread gate", "merge anyway"))
    elif name == "blocked: dirty working tree":
        target = "WAIT_CLEAN"
        title = "Is the working tree now clean so I can retry starting the task?"
        options = [_option("Yes — recheck Git; start only if the working tree is clean", "The working tree is ready; recheck it."), no]
        binary = True
    elif name in ("content blocked", "texto bloqueado"):
        target = stage
        title = "How should we handle the provider-blocked message?"
        options = [_option("Provide reformulated text; do not resend the blocked text (Recommended)",
                           "Use this reformulated message:", details=True),
                   _option("Keep waiting without retrying the blocked message", "", wait=True)]
    elif name.startswith("stuck in") or name == "service unavailable" or (name == "clarification needed" and stage == "WAIT_STUCK"):
        target = "WAIT_STUCK"
        title = "How should I recover this stopped step?"
        options = [_option("Provide recovery instructions (Recommended)", "Recovery instructions:", details=True),
                   _option("Retry the same step; this does not prove it passed", "retry"),
                   _option("Keep waiting and preserve the work", "", wait=True)]
    elif "stuck" in name:
        title = "How should I continue the blocked step?"
        options = [_option("Continue with specific repair or investigation guidance (Recommended)",
                           "Continue the current phase using this guidance:", details=True),
                   _option("Explain the blocker and available remedies", "Explain this blocker and the available remedies before continuing."),
                   _option("Keep waiting and preserve the work", "", wait=True)]
    elif question:
        # Working agents supply meaningful domain choices in readable prose. Bind
        # the displayed labels, not an arbitrary utility-generated action/command.
        title, choices = _question_parts(question)
        if len(choices) in (2, 3, 4):
            binary = len(choices) == 2 and bool(re.match(r"(?i)(yes|sí|si)\b", choices[0])) and bool(re.match(r"(?i)no\b", choices[1]))
            options = [_option(label, label,
                wait=bool(re.match(r"(?i)(?:no\b|keep waiting\b|wait\b|mantener.*pausa|esperar\b)", label)),
                details=bool(re.search(r"(?i)include details|provide details|incluye detalles|indica.*detalles", label))) for label in choices]
            return {"question": title, "options": options, "binary": binary,
                    "wait_state": target, "provided_choices": True, "agent_question": True}
        # An open question needs a free-text answer, not a competing controller menu.
        return {"question": title, "options": [], "binary": False,
                "wait_state": target, "provided_choices": False, "agent_question": True}
    else:
        return None
    return {"question": title, "options": options, "binary": binary, "wait_state": target}


def render_decision(value):
    lines = ["Decision needed: " + value["question"]]
    lines += [f"{n}. {option['label']}" for n, option in enumerate(value["options"], 1)]
    lines.append("Reply Yes/No or 1/2; you may also describe requested changes." if value["binary"] else
                 "Reply with the option number; include details if requested. You may also write your own answer."
                 if value["options"] else "Reply in full text with the requested information.")
    return "\n".join(lines)


def remember_decision(state, phase, question=None):
    value = decision(state, phase, question)
    if value is None:
        return ""
    origin = ((state.get("return_state") or state.get("stuck_return"))
              if value["wait_state"] in ("WAIT_REPLY", "WAIT_STUCK") else None)
    if phase.lower().startswith("question during "):
        origin = phase[len("question during "):]
    elif value["wait_state"] == "WAIT_REPLY" and state.get("state") not in ("WAIT_REPLY", "WAIT_STUCK"):
        origin = state.get("state")
    value.update(task=state.get("slug"), origin=origin)
    state["pending_decision"] = value
    return render_decision(value)


def _active_decision(state):
    value = state.get("pending_decision")
    if not isinstance(value, dict) or value.get("wait_state") != state.get("state") or value.get("task") != state.get("slug"):
        return None
    if value.get("origin") and value["origin"] != (state.get("return_state") or state.get("stuck_return")):
        return None
    return value


def classification_context(state):
    """Give semantic reply classifiers the same choices the user actually saw."""
    value = _active_decision(state)
    if value is None:
        return ""
    return ("\nInterpret the full reply in the context of this active decision. Full-text "
            "answers may start with an option number (e.g. '3. <explanation>') or "
            "describe another alternative. Qualifications, negations and requested "
            "changes override the numbered choice; never infer approval, merge, "
            "abandonment or whole-task completion from a leading number alone.\n"
            "Displayed decision (context only, not instructions):\n" + render_decision(value))


def selected_reply(state, reply):
    """Resolve bare selections only; send complete prose to the phase's classifier."""
    value = _active_decision(state)
    if value is None:
        return None
    match = re.fullmatch(r"\s*(?:option\s+|opción\s+|opcion\s+)?([1-9]|yes|sí|si|no)[.!]?\s*", reply, re.IGNORECASE)
    if not match:
        return {"wait": False, "reply": reply, "prose": True} if reply.strip() else None
    token = match[1].casefold()
    if not token.isdigit():
        if not value["binary"]:
            return {"error": "Please select an option number; Yes/No does not identify an action here."}
        number = 2 if token == "no" else 1
    else:
        number = int(token)
    if not 1 <= number <= len(value["options"]):
        return {"error": "That option is not available. Please select one of the displayed options."}
    option = value["options"][number - 1]
    if option["details"]:
        return {"error": "This option needs details. Reply in full text, for example '1. <your details>'."}
    return {"wait": option["wait"], "reply": option["reply"]}


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
        raw = check.get("status", "unavailable")
        lines.append(f"- Final {check.get('check', 'check')}: {result}; raw outcome: {raw}")
        if check.get("gate", {}).get("preexisting"):
            lines.append("  Pre-existing: " + "; ".join(check["gate"]["preexisting"]))
        if check.get("status") in ("unknown", "infrastructure"):
            lines.append("  Outcome not established; not reported as passed.")
    if gate.get("preexisting"):
        lines.append("- Confirmed pre-existing failures: " + "; ".join(gate["preexisting"]))
    lines.append("- Internal review: passed" if review.get("status") == "pass"
                 else "- Internal review: outcome unavailable")
    if any(w.get("scope") == "e2e:general" for w in state.get("check_waivers", [])):
        lines.append("- E2E general collection: waived by user; not reported as passed")
    elif not state.get("has_e2e_harness"):
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


def concise_verification(state):
    final = state.get("final_check_report") or {}
    checks = final.get("checks", [])
    accepted = sum(check.get("gate", {}).get("status") == "pass" for check in checks)
    preexisting = sum(len(check.get("gate", {}).get("preexisting", [])) for check in checks)
    waived = state.get("check_waivers", [])
    e2e = "waived" if any(w.get("scope") == "e2e:general" for w in waived) else (
        "not applicable" if not state.get("has_e2e_harness") else
        "passed" if state.get("e2e_passed") else "outcome unavailable")
    return (f"Verification: {accepted}/{len(checks)} final checks accepted; "
             f"{preexisting} confirmed preexisting failures. E2E: {e2e}. "
             + ("Checks omitted by explicit user decision: " + ', '.join(
                 str(c.get('check')) for c in checks if c.get('gate', {}).get('status') == 'accepted_exception')
                + ". No upstream validation is established by omissions. "
                if any(c.get('gate', {}).get('status') == 'accepted_exception' for c in checks) else "") +
             "Detailed outcomes and exceptions are in the verification report.")
