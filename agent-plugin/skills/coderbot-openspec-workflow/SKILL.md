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

## Headless Input

For a truly material unresolved decision, return `NEED_USER_INPUT` with the decision, options, and impact. Do not ask an interactive question. Otherwise continue autonomously within the current phase.

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
