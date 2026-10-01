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

Routine milestone images and working check-ins are suppressed. Decision reminders
are short and due after 24 hours; `CODEBOT_PING_SCHEDULE=off` disables them.
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
