---
name: coderbot-openspec-workflow
description: Use when a headless coderbot agent is working on an OpenSpec-managed change
---

# Coderbot OpenSpec Workflow

## Overview

Honor the orchestrator boundary while applying OpenSpec and Superpowers exactly where they own the work. OpenSpec owns requirements, design, and tasks; coderbot owns branch, state, email approvals, archive timing, push, PR, and merge; Superpowers owns engineering discipline.

Use the checkout coderbot supplied. Treat approved OpenSpec artifacts as the only plan.

## Quick Reference

| Phase | Contract |
|---|---|
| EXPLORING | The agent uses `openspec-explore`; OpenSpec holds discoveries and coderbot controls transition. |
| PROPOSING | The agent uses `openspec-propose`; OpenSpec holds proposal, design, specs, and tasks; coderbot obtains approval. |
| IMPLEMENTING | The agent uses `openspec-apply-change` and required Superpowers skills, including `test-driven-development`; coderbot owns state. |
| VERIFYING | The agent runs focused checks and validates OpenSpec; coderbot owns the complete final suites and baseline comparison after independent review. |
| INTERNAL_REVIEW | The agent obtains a fresh internal review using `requesting-code-review`. Prior test evidence and future external review are not substitutes; coderbot owns remediation state. |
| E2E repair | Repair only confirmed new regressions using focused checks, obtain independent re-review of the fix, and let coderbot invalidate affected checks before the final gate. |
| ARCHIVING / OPEN_PR | Coderbot alone chooses archive timing, archives, pushes, creates the PR, and requests merge approval. |

## Hard Boundaries

The agent must never push, create a PR, merge, choose archive timing, finish the branch, or choose a merge strategy.

Stop after reporting phase output and evidence; coderbot performs lifecycle side effects.

Never kill unknown/human processes to repair a port collision. Prove ownership or
choose isolated ports/workspaces. Local repair does not authorize IAM changes,
privilege expansion, paid provider calls, remote data mutations or deployment.
Ask for specific authorization when those effects are indispensable; preserve
work and offer local alternatives rather than fabricating remote validation.

## Headless Input

For a truly material unresolved decision, return `NEED_USER_INPUT` with the decision, options, and impact. Do not ask an interactive question. Otherwise continue autonomously within the current phase.

## Integration Evidence

Before dependent design, inspect declared, installed and deployment versions and official documentation for the exact SDK/library version and endpoint. Record source URL, consultation date and relevant evidence; `latest` documentation does not establish old-version compatibility. Inspect actual internal handlers, schemas and consumers instead of inventing response shapes. Record contracts for routing, authentication, isolation, parameters, responses and errors; resolve documentation/code/runtime contradictions and material assumptions explicitly.

Detect missing credentials early. Explain least privilege, environment, checks, effects and any paid-call budget. Offer secure provisioning, continuing without credentials by explicitly omitting dependent live validation and using alternatives, or pausing. Honor controller-recorded exceptions across recovery; no repeated key request for unchanged scope. Refusal plus continuation is not task completion, merge/deployment approval or authorization to relax security/retention. Local tool permission does not prove external IAM access or authorize paid inference.

Fixtures derive from investigated contracts and reject incorrect auth/routes/params. Verify outbound requests and parameter preservation; local/mock success and model listing do not establish live inference/tools/streaming/resumption. Revalidate after material endpoint/version/scope changes. Report local, upstream, deployment and postdeployment evidence separately; skipped or omitted checks never count as pass.

## Parallelism

Wall-clock time is the cost that matters in a headless run. Whenever work splits into independent parts, fan it out to multiple subagents launched together in one message and integrate the results; batch independent tool calls into one message. Typical fan-outs per phase:

| Phase | Fan out |
|---|---|
| EXPLORING | One subagent per affected area (data model, API, UI, tests, conventions). |
| IMPLEMENTING | One subagent per independent `tasks.md` task, each doing strict TDD; serialise only dependent tasks. |
| VERIFYING | Request independent focused checks with CHECK_PLAN; do not rerun full suites or baseline work already owned by coderbot. |
| INTERNAL_REVIEW / review threads | Unrelated findings or threads fixed by separate subagents. |

Serialise only steps that genuinely depend on an earlier result. Parallel subagents inherit every hard boundary above.

## Strict TDD

Use test-driven-development for new behavior. On recovery inspect durable RED/GREEN evidence, completed tasks and the actual diff first. Preserve valid work from previous attempts; do not delete or rebuild implementation solely because the current session did not witness its tests. For unknown or incomplete work, diagnose and run focused coverage, then repair minimally. Report missing TDD evidence honestly rather than inventing it.

## Rationalization Counters

| Excuse | Reality |
|---|---|
| "Restart all work after KICK." | Preserve valid checkpoints and RED/GREEN evidence; repair only incomplete work. |
| "The work is verified, so I can open the PR." | Verification produces evidence; coderbot owns every lifecycle side effect. |
| "Archiving is the obvious next step." | Only coderbot selects archive timing and enters `ARCHIVING / OPEN_PR`. |

## Red Flags

- Inventing RED/GREEN evidence or discarding valid work merely because a session restarted
- Any agent-run archive, push, PR, merge, or branch-finishing command
- Any merge-strategy recommendation

Stop and return control to coderbot when any red flag appears.

## Example

In `IMPLEMENTING`, recover partial code: inspect checkpoints, run focused checks for incomplete behavior, repair minimally and hand control back to coderbot.

## Common Mistakes

- Treating phase completion as permission to advance the workflow
- Rebuilding previous-agent work without examining its checkpoint evidence
