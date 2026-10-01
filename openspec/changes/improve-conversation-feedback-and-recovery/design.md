## Context

See proposal.md for motivation and the six delta capabilities for behavior. `main.py` owns a single-threaded FSM while a status supervisor reads shallow snapshots and serves STATUS/KICK. Communication is selected through `conversation.py`, exposed in main as `gmail_client`; Email and Slack already accept `Path` attachments but return only a thread id. Slack swallows upload errors and Email omits oversized attachments. Recovery instructions inherit phase rules, archival retries a dirty precondition without repair, PR feedback is classified without requirements context, and some recovery paths ignore agent questions. Existing execution/checkpoint stores provide task identities and content-bound results.

## Goals / Non-Goals

**Goals:** Preserve single-owner FSM mutation while receiving feedback promptly; make approval, recovery and delivery restartable; reuse existing stores, report files and proposal packaging; replace unstructured historical text with current structured facts.

**Non-Goals:** Add Telegram now; reset or merge the live target PR as part of coding this change; rewrite target archive history; add concurrent coding turns; guarantee exactly-once delivery where a provider cannot reconcile an uncertain send.

## Decisions

### Durable feedback ledger and safe-boundary dispatch

Introduce task-bound feedback records containing message/channel/thread ids, original text, receipt time, status, assessment, requirement references and outcome. Receive/acknowledge without mutating the main FSM from the status thread: use the communication inbox and execution store for durable events, then drain them at main-thread safe boundaries. Inbox deduplication and a handling checkpoint prevent replay. Check user messages before PR-thread polling and conflict dispatch. Email reception must also operate during long turns, within existing polling limits. Preserve command targeting and authorized-sender rules. Purely polling replies in WAIT states was rejected because it recreates the missing-dropdown delay.

Assessment is a structured, schema-validated utility result informed by actual artifacts and a bounded investigation of current implementation: question answer, correction, material change or unresolved decision, with reasoning and references. Mixed question/requirement input retains both. Record pending work until its resulting repair, answer or proposal handoff is delivered; a successful classifier is not completed feedback.

### Explicit replanning continuation

Add a replan state/continuation distinct from initial PROPOSING so `_undo_premature_work` never resets legitimate implementation. Store origin phase, feedback ids, reviewed artifact fingerprint, retained implementation snapshot and existing PR. For active changes revise current artifacts; for archived changes scaffold a linked complementary change through OpenSpec and point the task's planning context to it while retaining prior archive/PR references. Generate the existing full HTML package and an actual revision summary. Clear only superseded consent and content-bound reports; retain durable feedback and implementation. Approval resumes task implementation, verification and appropriate archival/update paths rather than blindly rerunning initial PR creation. Fingerprint consent to reviewed proposal and PR content. Automatically dropping the prior work or treating all feedback as direct PR edits was rejected.

### Cross-phase recovery with provenance and progress

Introduce a recovery record with incident id, original condition, origin/resume target, repository snapshot, repair plan, attempt and progress fingerprints. Record task-start Git state including index, unstaged/untracked paths and operation markers; record turn deltas thereafter. Use machine-readable NUL-delimited Git status for filenames and inspect in-progress operations before acting. Repair task-owned changes and commit only intended paths after verification; use recovery-specific authorization instead of ARCHIVING-only OpenSpec rules. Preserve unrelated/ambiguous changes using a task-specific isolated worktree; prepare that workspace and ensure every agent/check command uses its resolved path. Migration cannot manufacture provenance for old changes: inspect session/transcript/commit evidence and use preservation/isolation when attribution remains uncertain.

Every recovery result passes through common question/result handling; a question retains both recovery origin and its own continuation. Check failed preconditions after repair and invalidate affected verification. Fingerprint unchanged failures to detect no-op loops; product ambiguity becomes a specific question or replanning, infrastructure unavailability stays technical. Blind `reset --hard`, indiscriminate commits and global stash cleanup were rejected.

### Typed attempts and bounded retries

Represent agent connectivity failures with a typed error retaining original diagnostics and classify known transport causes, including OpenCode fetch failure, separately from schema/program errors. Keep technical retries separate from completed functional rounds and increment a round only after a valid result. Use configurable bounded exponential backoff with cancellation/hold support and a persistent incident lifecycle; notify once after sustained unavailability and update only meaningful recovery changes. Unknown errors retain diagnostics and prompt diagnosis rather than being treated as connectivity by broad string matching.

### Channel-neutral outgoing envelope and receipts

Add an outgoing message envelope with stable notification id, short subject/body, thread, attachment descriptors and per-artifact receipt state. Descriptors include id/hash, path, filename, media type, size and role (diagnostic/proposal/evidence); receipts include confirmed provider ids, pending/failed/uncertain status and retry detail. Keep a compatibility wrapper for existing `send` callers while main delivery adopts detailed receipts. Adapters expose actual per-file/per-message limits and reconciliation capabilities.

Generate redacted UTF-8 incident reports before summary localization; preserve full exception chains and command output in data storage outside the target checkout. Redact configured credential values and common token/header patterns, retaining structural placeholders. Do not use pass-only evidence filtering for diagnostics. Preflight size limits; gzip oversized reports and, if necessary, create numbered lossless parts with a manifest. Email MIME accounting includes encoding overhead and message-wide caps; large sets use additional task-thread messages. Slack uploads files separately and stores each receipt. Retry unresolved attachments without repeating confirmed files or coding phases; reconcile uncertain provider sends where possible, otherwise record uncertainty explicitly instead of asserting exactly-once delivery. File generation, upload and short-body notification have separate checkpoints. Purely truncating bodies at Slack's chunk limit was rejected because it loses useful detail and ignores Email.

### Structured verification and intent-aware review

Create a requirement coverage ledger from approved spec scenarios/tasks with implementation, verification and evidence references and current content fingerprint. Validate it at delivery and route material omissions into repair/replan. Store scoped waivers with original message, reason, command/collection selector and reviewed version; a general E2E waiver does not silently waive feature checks. Model raw check status separately from gate acceptance (e.g. raw failures with confirmed baseline evidence), so accepted preexisting failures are not described as all tests passing. Reuse valid content/environment-bound results only; invalidation after repair targets affected checks with conservative fallback when dependencies are unknown.

Review records retain provenance (provider author type, known workflow/configured accounts and markers), semantic disposition and requirements references. Unknown authors remain unknown. Conflicting suggestions require evidence-based reasoning or replanning rather than mechanical edits. Summaries reference current facts and identify significant unresolved blockers with a recommendation; full review lists and verification logs are reports. Required verification repairs remain in shared commits or tracked follow-ups.

### Event-driven presentation and accurate contact

Use typed message purposes and deterministic English/Spanish operational templates; task-specific prose uses a bounded utility fallback. Render roughly 6–10 lines for normal events and move detail into indexed attachments. Suppress routine phase images/announcements and unchanged architecture notices. Keep one 24-hour reminder per unchanged decision; decision identity resets the reminder, normal work does not trigger reminders. STATUS combines live execution snapshots with last effective progress and retry/wait information. Supervisor contact updates become durable events applied by the FSM owner, avoiding stale state overwrite. Do not include original full bodies in reminders or duplicate stack traces in trail copy.

## Risks / Trade-offs

- [Legacy work ownership is incomplete] → Preserve and isolate ambiguous changes; migrate incrementally without discarding files or invented attribution.
- [Replanning after archive may interact with archive/PR guards] → Persist both original delivery references and complementary planning identity; test the complete post-PR lifecycle.
- [Provider send succeeds before receipt persistence] → Stable ids and provider reconciliation where supported; expose uncertainty and avoid claiming confirmed delivery prematurely.
- [Classification misses materiality] → Require artifact/code references, validate utility schemas and use the exact dropdown incident as a regression; uncertain product decisions are explicit.
- [Redaction or splitting hides useful diagnostics] → Lossless structural reports, reconstruction tests and secret fixtures; configured-value redaction applies before compression.
- [Isolation breaks prepared environments] → Resolve workspace paths through agent/check contexts and rerun environment probes, never assume dependencies are reusable across worktrees.
- [Large scope changes existing behavior] → Implement independent modules behind common contracts, validate migration and preserve existing approval/thread/authorization semantics.

## Migration Plan

1. Add versioned feedback/recovery/incident/receipt records with defaults for active and held tasks; keep existing state readable and back up durable stores before upgrading a deployment.
2. Introduce contracts and deterministic tests, then wire the main FSM safe-boundary dispatch, replanning and recovery.
3. Adopt structured delivery/check reporting and new adapters incrementally with compatibility wrappers; disable old images/working pings by default and document replacement settings.
4. Run targeted tests, full `python3 -m unittest discover -s tests -t .`, strict OpenSpec validation, controlled Email/Slack attachment checks and restart/migration scenarios.
5. For an authorized live rollout, inspect bot source changes, save current state and inspect target Git operation/provenance before stopping/restarting the service. Smoke-test STATUS and attachment delivery; resume PR #101 through the recovery path, never by resetting the checkout or marking it complete.
6. Roll back code only with compatible store readers; preserve pending feedback, artifacts and delivery records. Do not reset durable task state as a rollback mechanism.
