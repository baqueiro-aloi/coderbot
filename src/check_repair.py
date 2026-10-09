"""Bounded final-check diagnosis; agent prose never overrides controller evidence."""
import json

import prompts


def unresolved(report):
    return [item for item in report.get("checks", [])
            if item.get("status") != "pass" or item.get("gate", {}).get("status") != "pass"]


def prompt(state, context):
    return (prompts.ENVIRONMENT + "\nFinal-check recovery, attempt "
            + str(context["attempt"]) + ": diagnose BEFORE retrying.\n"
            "Read every unresolved check's actual report below. Identify the exact cause, "
            "not merely 'indeterminate'. Repair execution dependencies, missing declared "
            "packages, virtualenv/interpreter selection, services, permissions or runner "
            "configuration autonomously in this trusted runtime. For example, if pytz is "
            "declared but absent, install the declared dependencies in the SAME interpreter "
            "used by the controller check; prove the import works there. Installing into "
            "another interpreter does not repair this check. Do not ask the user to SSH, "
            "edit the bot, install packages or approve tools.\n"
            "The default response to EVERY failure is IMPLEMENT A FIX, not ask the user "
            "what to do. Repair code/tests/runner defects, including inherited defects "
            "that block the requested checks, within the approved intent. "
            "Preserve implementation, unrelated work and Git history. Commit intended "
            "tracked repairs locally on the task branch; never push, merge a PR, rewrite "
            "scope/approval or disable checks/rules. Do not fix an unrelated historical "
            "defect or change product behavior without a concrete scope decision.\n"
            "The immutable comparison base is " + str(state.get("base_sha", "unavailable"))
            + ". Current main/origin/main is NOT a replacement base. A failure introduced "
            "by an integrated upstream commit may be inherited, but remains unresolved "
            "until repaired. Your authorization already covers fixing the requested "
            "tests/runner behavior; do not request another approval for the same scope. "
            "Never mark infrastructure failures, unknown output, absent baseline dependencies "
            "or a prose comparison as passed/preexisting/waived. If baseline dependency "
            "inputs differ, read the baseline preparation log and repair the missing "
            "runtime prerequisite; do not modify the "
            "immutable base or fabricate comparison results.\n"
            "Run minimal focused diagnostics/probes to prove the repair. Do NOT rerun "
            "full suites or baseline suites: after your turn the controller reruns "
            "unresolved checks and reuses valid unaffected checks. A previous no-change "
            "attempt is not progress: change the diagnosis/repair approach or ask one "
            "concrete human decision with 2-4 options and consequences. Never just "
            "recommend ignoring errors or repeating the same check.\n"
            + prompts.fenced("unresolved controller check results", json.dumps(context["checks"], ensure_ascii=False))
            + "\n" + prompts.fenced("previous repair findings", context.get("previous", ""))
            + ("\n" + prompts.fenced_authoritative("user recovery guidance", context["guidance"])
               if context.get("guidance") else "")
            + "\nEnd with a readable summary of exact causes, repairs, diagnostic "
            "commands/results and what remains unresolved. Attach supporting evidence. "
            "Do not emit a completion/pass contract; only controller-run checks can "
            "approve the final gate. If a human choice is essential, use NEED_USER_INPUT "
            "with concrete options; a bare 'ignore' must never waive the final gate.\n")


def summary(report):
    lines = ["Final checks need diagnosis/repair (not a new implementation plan):"]
    for item in unresolved(report):
        gate = item.get("gate", {})
        lines.append(f"- {item.get('check', 'check')}: {item.get('status', 'unknown')}; "
                     f"gate={gate.get('status', 'indeterminate')}"
                     + (f"; reason={gate['reason']}" if gate.get("reason") else ""))
    return "\n".join(lines)
