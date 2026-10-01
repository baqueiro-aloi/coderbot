# Conversation, diagnostics and recovery

Durable task events are stored in `data/execution.sqlite`; diagnostic files live in
`data/diagnostics/`. Existing schema-v1 tables remain readable. Added tables store
feedback, recovery, incidents, contacts, provenance and attachment receipts. Task
identity is retained when the task moves to an isolated workspace.

## Diagnostic attachment contract

`conversation.deliver(state, subject, body, thread_id, attachments)` returns a thread
id, aggregate completion and per-artifact receipts. `conversation.send` remains the
legacy simple interface. Detailed adapters implement:

- `attachment_limits()`: file budget and whether MIME encoding applies.
- `send_envelope(envelope, receipts, confirm)`: checkpoint file/body outcomes.
- `reconcile_delivery(envelope, key, receipt)`: reconcile uncertain acceptance.

Descriptors carry content identity, filename, MIME type, size, path and role.
Receipts distinguish confirmed, failed and uncertain sends. Failed uploads retry
independently, without resending confirmed files or rerunning the coding agent.
Slack can reconcile thread files/messages. Email envelopes use a stable Message-ID
and Gmail sent-message lookup to reconcile acceptance. If a provider cannot establish
the outcome, the receipt remains uncertain instead of blindly duplicating a send.

Oversized artifacts are gzip compressed or split into numbered parts and a manifest.
Concatenate split parts numerically, then gzip-decompress; verify the original SHA-256
from the manifest. Email sends each file in a separate threaded message within its
MIME budget. Reports preserve full available exception chains and subprocess outputs
with credential/token redaction; failed executions do not disqualify diagnostics.

## Defaults

OpenCode persists the root session ID as soon as the invocation emits it. A
connection failure, timeout or process restart resumes that session for the same
task, phase and request, preserving history and partial repository work. Recovery
asks the agent to reuse completed findings and subagent results and check pending
commands before repeating them. Completed outcomes still replay without invoking
the agent. Only a missing OpenCode session falls back to reconstructing context
from the repository and OpenSpec artifacts.
Retry delays start at 1 second and double (2, 4, 8, …), capped at 3600 seconds
and subject to the existing consecutive-failure limit. The task's network retry
counter and next retry time survive restarts; a successful phase resets them.
The ordinary backlog poll interval does not delay a retry that is due sooner.
The HTTP bridge submits turns through `prompt_async` and polls session status
with short requests while streaming tool events. Long turns therefore do not
depend on a single HTTP response surviving Node's five-minute headers timeout.
Resumed sessions register existing child sessions for event tracking. Subagent
limits measure inactivity and refresh on that child's progress; the aggregate
agent-turn deadline remains fixed. Operation timeouts report the actual expired
operation and its limit instead of always reporting the global agent timeout.

Each task state entry sends a lifecycle banner in the task thread, including
returns to earlier states. States within a lifecycle step share its illustration
and name the exact FSM state in the notice. Pending banners retry on the next tick;
restarts and retries within the same state do not repeat delivered banners. Email
renders the banner inline; Slack shares the PNG in the thread. Review packages keep
their delivery receipts and share their banner in a separate threaded message.
Questions remain visible in the message even when the investigation is moved to
a diagnostic attachment. The full pending question is retained for reply context;
state banners do not replace the substantive last message used by STATUS.
Attached `.log` reports are delivered as `.txt` with `text/plain` MIME type so
Slack and email can preview them; the original file and full bytes are preserved.
Routine working check-ins are suppressed. Decision reminders are short and due after 24 hours;
`CODEBOT_PING_SCHEDULE=off` disables them.
`CODEBOT_SLACK_MAX_ATTACH_BYTES` defaults to 104857600. Email uses the existing
`CODEBOT_MAX_ATTACH_BYTES` with encoding headroom. STATUS records contact events
which the FSM owner applies without supervisor state overwrites.

## Deployment/recovery runbook for PR #101

Run these steps when a live rollout is requested. Unit/integration scenarios cover
preservation, restart, complementary proposals and adapter receipts without accessing
the production task.

1. Inspect `/home/azureuser/codebot/app` status/diff and preserve host-specific edits.
2. Stop `app-codebot-1` so state and Git remain stable during backup/inspection.
3. Back up all `app/data/`, including SQLite/WAL/SHM, active/held state and artifacts.
   Preserve staged/unstaged target diffs, untracked files, branch/head and Git metadata.
4. Inspect `/home/azureuser/codebot/target` for MERGE_HEAD, rebase and cherry-pick
   metadata; attribute repairs using task commits and transcripts. Do not reset/clean
   the target or delete state to unblock it.
5. Install verified sources, preserve `.env`, rebuild when dependencies require it,
   restart and check health/runtime logs.
6. Send STATUS in the existing task thread; verify task/PR linkage and recovery.
   Verify downloadable diagnostic contents and failed-file retries in each channel.
7. Resume the blocker through recovery, preserving work and attending dropdown feedback
   before further review/conflict work. Do not mark complete or merge to bypass errors.
8. Roll back compatible sources while preserving newer feedback/decisions/diagnostics
   and receipts. Inspect uncertain sends before replay; do not overwrite newer state
    with an old snapshot as a shortcut.

## Verification

Use the repository's dependency-equipped interpreter and full suite:

```sh
venv/bin/python -m unittest discover -s tests -t .
openspec validate improve-conversation-feedback-and-recovery --strict
```

`test_recovery_integration` exercises real Git repair commits and interrupted merges;
`test_recovery_worktree` verifies isolation leaves the original index and files intact.
`test_replanning_lifecycle` exercises complementary proposal packaging and approval.
`test_conversation_flow` exercises both adapters with controlled APIs; MIME tests
verify complete downloadable Email payloads. Live provider delivery smoke checks
remain part of deployment, rather than sending unsolicited production messages.
