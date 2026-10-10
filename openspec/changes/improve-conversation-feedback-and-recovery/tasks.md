## 1. Durable records and compatibility

- [x] 1.1 Add versioned task-bound feedback, recovery, incident and delivery receipt records using the existing execution store and stable identities.
- [x] 1.2 Migrate active and held legacy tasks without losing pending questions, PR linkage, session, feedback or stored artifacts; test restart and rollback-readable state.
- [x] 1.3 Record task-start Git/index/untracked/operation provenance and turn-bound content changes without touching unrelated work.

## 2. Diagnostic artifacts and communication contract

- [x] 2.1 Generate persistent redacted UTF-8 reports preserving full tracebacks, exception chains and available command/stdout/stderr context; test long traces and credential fixtures.
- [x] 2.2 Add channel-neutral attachment descriptors, outgoing envelopes and detailed per-artifact receipts while preserving existing send/proposal/evidence interfaces.
- [x] 2.3 Implement adapter-aware attachment sizing, MIME overhead budgeting, gzip compression and numbered lossless parts/manifests; test reconstruction and message-wide limits.
- [x] 2.4 Implement Email detailed delivery and task-thread follow-up files without silently omitting diagnostics; test MIME attachments and pending/uncertain sends.
- [x] 2.5 Implement Slack detailed file receipts and independent retries; test accepted-body/failed-upload, partial success and restart reconciliation without duplicate confirmed files.
- [x] 2.6 Wire agent, checks, recovery, archival and Git/PR failures to reports and short notifications; eliminate traceback excerpts and serialized test dumps from outgoing bodies.
- [x] 2.7 Persist silent retry diagnostics and delivery work independently from functional phase completion; ensure failed-run reports remain eligible for attachment.

## 3. Feedback reception and investigation

- [x] 3.1 Receive and deduplicate authorized task-thread messages during active turns in Email and Slack, preserving command targeting and recording feedback before acknowledgment/consumption.
- [x] 3.2 Dispatch pending feedback at main-thread safe boundaries before review/conflict work, without concurrent coding turns or supervisor state overwrites.
- [x] 3.3 Add validated impact assessment informed by actual approved artifacts and implementation, preserving both questions and requirement assertions in mixed messages.
- [x] 3.4 Deliver factual answers and retain pending feedback until its answer, repair or revised proposal handoff is completed; test restart, hold and failed delivery.
- [x] 3.5 Add the exact missing-model-dropdown message as a regression covering precedence over automated threads and investigation rather than unclear-command fallback.

## 4. Replanning and versioned approval

- [x] 4.1 Add a replanning state/continuation preserving origin, implementation, feedback and PR references and suspending incompatible autonomous work.
- [x] 4.2 Revise active proposal/design/spec/tasks for material feedback and bypass premature-work cleanup for legitimate implementation.
- [x] 4.3 Scaffold a linked complementary OpenSpec change for archived work, retain historical archive and existing PR, and package the full revised proposal with actual differences.
- [x] 4.4 Bind approval and merge consent to reviewed content, invalidate superseded consent and require revised approval before implementing material changes.
- [x] 4.5 Resume implementation, affected verification/demo, archival and PR updates correctly after revised approval without recreating the original task or PR.
- [x] 4.6 Test post-PR selector replanning, preservation of commits/uncommitted legitimate work, rejected stale merge, and localized corrections that do not require reapproval.

## 5. Autonomous repository and phase recovery

- [x] 5.1 Add recovery condition/origin/resume records and progress fingerprints; replace repeated failed preconditions with diagnosis and recovery routing.
- [x] 5.2 Inspect staged, unstaged, untracked and incomplete Git operations with robust path handling; test filenames with spaces and task-owned interrupted merges.
- [x] 5.3 Review, verify and commit task-owned test repairs before archival using recovery-specific rules rather than OpenSpec-only restrictions.
- [x] 5.4 Preserve ambiguous/unrelated edits through task worktree isolation and route agent/check/preparation contexts to the isolated workspace.
- [x] 5.5 Process recovery questions through shared result handling with intact blocker and continuation; verify the repaired condition before clearing it.
- [x] 5.6 Persist required verification repairs in task history or tracked linked work, invalidate affected reports and test restart/no-op recovery detection.

## 6. Technical retries and completed rounds

- [x] 6.1 Add typed agent transport failures and classify OpenCode fetch errors without conflating schema/product/unknown failures.
- [x] 6.2 Persist bounded increasing-delay technical retry state with hold/cancel support and one sustained-unavailability incident notice.
- [x] 6.3 Move functional round accounting to valid completed results for automated and PR-thread review; test repeated fetch failures leaving round counts unchanged.

## 7. Requirement coverage, waivers and review intent

- [x] 7.1 Build a current approved-requirement coverage ledger with implementation, verification and evidence references; gate delivery on material omissions.
- [x] 7.2 Record explicit waiver scope/reason/original instruction/version and distinguish waived general E2E from passing feature-specific checks.
- [x] 7.3 Render raw outcomes separately from gate acceptance and preserve baseline evidence, content/environment identities and affected-check invalidation.
- [x] 7.4 Identify human/automated/unknown review provenance and assess findings against approved intent, with evidence-backed fixes, explanations or replanning.
- [x] 7.5 Produce attached detailed review/verification reports and concise prioritized unresolved-blocker recommendations; align merge/merge-anyway text with enforced semantics.
- [x] 7.6 Test approved-high-effort versus suggested-medium conflict, automated reviewer labeling, absent selector despite passing tests and indeterminate-versus-preexisting results.

## 8. Concise event-driven presentation

- [x] 8.1 Add purpose-based English/Spanish operational templates and bounded utility localization with original-language fallback and no diagnostic translation.
- [x] 8.2 Remove routine standalone milestone images/administrative notices and working pings; implement one short 24-hour reminder per unchanged decision.
- [x] 8.3 Apply supervisor contact events safely for STATUS/KICK and show live execution, effective progress, retry/wait condition and precise user action.
- [x] 8.4 Build PR delivery and feedback summaries from current structured facts and confirmed attachments rather than obsolete agent narration.
- [x] 8.5 Suppress empty/unchanged architecture notices while attaching or linking supported important findings and preserving independent replanning rules.
- [x] 8.6 Test bounded normal message length, no previous-body quotation, no tracebacks in bodies, truthful attachment labels and contact-clock behavior.

## 9. Integrated verification and operational readiness

- [x] 9.1 Exercise controlled end-to-end Email and Slack lifecycle scenarios covering active-turn feedback, replanning, repair, delivery failure and restart.
- [x] 9.2 Run `python3 -m unittest discover -s tests -t .` and fix regressions in existing approval, thread ownership, evidence, archival and checkpoint behavior.
- [x] 9.3 Run strict OpenSpec validation and update README/configuration/adapter contract documentation with changed defaults, receipts, recovery and migration behavior.
- [x] 9.4 Document a verified deployment/recovery runbook for the current WAIT_STUCK PR #101 including source/state backup, Git operation inspection, service restart, smoke checks and compatible rollback; keep execution gated on an explicit live rollout request.

Verification: dependency-equipped `venv/bin/python -m unittest discover -s tests -t .`
completed with 677 tests, OK (1 skipped). Controlled Email MIME and Slack API fixtures,
real Git repair/isolation/merge scenarios, durable restart and complementary proposal
tests passed. `openspec validate improve-conversation-feedback-and-recovery --strict`
passed. Live rollout and provider smoke checks are documented, not executed.

## 10. Full-text decision and initial-planning regression

- [x] 10.1 Preserve full-text answers for all multiple-choice handoffs and provide active displayed choices to semantic classifiers without turning qualified prose into automatic approval, merge or waiting.
- [x] 10.2 Resume initial exploration/proposal clarification and queued feedback in the same phase without assuming approved OpenSpec artifacts; preserve post-approval scope assessment.
- [x] 10.3 Test the exact optional asynchronous logging reply, qualified controller decisions, restart/queued feedback and initial PROPOSING transition; run regression suites and strict OpenSpec validation.

Regression verification (2026-10-07): 33 focused tests passed; final
`venv/bin/python -m unittest discover -s tests -t .` completed with 804 tests,
OK (1 skipped). Strict validation passed. No live rollout or task-state repair executed.

## 11. Single decision handoffs

- [x] 11.1 Normalize inline and multiline real options into separate lines, preserve their task-bound meaning, and avoid generic menus for supplied concrete/open questions.
- [x] 11.2 Render the actionable question once while preserving useful context and attachments; instruct agents to ask one decision then stop and wait.
- [x] 11.3 Cover the duplicated OpenSpec authorization in Email and Slack, inline options, open questions and technical payload preservation; run full regression tests and strict validation.

Verification (2026-10-07): `venv/bin/python -m unittest discover -s tests -t .`
completed with 807 tests, OK (1 skipped). Strict OpenSpec validation and
`git diff --check` passed. No live rollout or state changes executed.

## 12. Concise approval waits

- [x] 12.1 Classify approval deferrals separately from substantive revisions and preserve the waiting proposal without another agent turn.
- [x] 12.2 Deduplicate reviewed packages by artifact fingerprint, replace full agent narration with a short change summary and keep approval reminders concise.
- [x] 12.3 Cover deferral, unchanged-package retries, long narration and reminders; run regression suites and strict validation.

Verification (2026-10-07): full unittest discovery completed with 812 tests,
OK (1 skipped). No live deployment or task-state repair executed.
