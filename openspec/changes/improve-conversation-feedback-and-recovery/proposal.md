## Why

The incident in `convo.txt` shows coderbot delivering contradictory reports, delaying product feedback, repeating technical failures, and requesting help for its own dirty worktree. The user needs an agent that advances toward approved requirements, repairs its mistakes across phase boundaries, and provides concise messages with complete diagnostic attachments.

## What Changes

- Persist and prioritize user feedback in every active phase, distinguish questions from requested changes, and investigate impact against approved artifacts and actual implementation.
- Replan material omissions and scope/design changes, preserving implemented work and requiring approval of the revised plan before further implementation or merge.
- Introduce checkpointed cross-phase recovery for task-owned changes, incomplete Git operations and failed phase preconditions; preserve unrelated work through isolation.
- Separate technical attempts from completed review rounds, handle transient agent connectivity failures, and process questions produced during recovery.
- Send event-driven, concise messages with accurate contact/status information; remove routine stage images and repeated full-message reminders.
- Generate durable, complete diagnostic files and deliver them through a channel-neutral attachment contract, with per-file delivery tracking, retries and size handling for Email and Slack.
- Verify requirement coverage and report snapshot-bound outcomes and explicit check waivers rather than historical summaries or misleading success labels.
- Evaluate automated review findings against approved intent, identify reviewer provenance accurately, and summarize actionable blockers rather than dumping comments or suggesting unexplained bypasses.
- **BREAKING**: routine visual milestone announcements and periodic working check-ins are replaced by important-event messages and on-demand STATUS; material feedback invalidates superseded approval/merge instructions.

## Capabilities

### New Capabilities

- `feedback-replanning`: durable, priority feedback handling and versioned replanning after substantial product feedback.
- `autonomous-recovery`: checkpointed recovery across phases, work provenance, preserved Git state and separate technical retry budgets.
- `diagnostic-attachments`: complete incident reports and reliable channel-neutral attachment delivery.

### Modified Capabilities

- `lifecycle-communication`: concise important-event messages, truthful status, bounded reminders and current delivery summaries.
- `quality-gates`: requirement coverage, snapshot-bound outcomes, scoped waivers and intent-aware review handling.
- `architectural-decision-report`: retain evidence-backed architectural reporting without empty or repetitive standalone notices.

## Impact

Affected areas include `src/main.py`, prompts, task handoffs, checkpoints, agent execution, Git/worktree recovery, check reports, artifact persistence, `conversation.py`, Email and Slack adapters, templates, configuration and operational documentation. Additive durable state and delivery records must migrate existing active and held tasks without resetting them. Existing proposal HTML and evidence delivery remain supported. No new Telegram adapter is in scope, but future adapters must satisfy the attachment contract. Verification uses deterministic unit/integration tests and controlled channel delivery checks before any live deployment or recovery of PR #101.
