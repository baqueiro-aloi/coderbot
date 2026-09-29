## Why

Codebot's email and Slack conversations expose raw agent output, long technical status messages, and evidence without a compact guide to the user's next decision. Reviewers also cannot easily see how a revised proposal changed or which significant architectural choices the implementation actually made. Make each handoff readable and actionable without changing the existing approval, verification, review, or merge gates.

## What Changes

- Announce each major task milestone once in its conversation thread with a short message and a pregenerated progress illustration, from exploration through a confirmed PR merge. Reuse existing handoff messages when they already announce that milestone; keep questions, retries, and silence check-ins free of repeated milestone images.
- Attach one offline, self-contained, navigable HTML document containing the complete OpenSpec proposal, design, tasks, and nested spec files at initial proposal review and after each revision. Summarize substantive changes from the previous version in revision messages.
- Put a concise, channel-appropriate decision card at the top of messages requiring the user's input; preserve the current reply semantics. Send a human-readable verification summary, PR-review cover note, structured feedback-applied recap, and an index explaining available evidence.
- Immediately after opening a PR, send a separate, short, informational list of high-impact implemented architectural decisions and unconfirmed assumptions, distinguishing previously approved choices from additions. Link every reported item to actual changed files and compare against OpenSpec; if later review changes one materially, report only that delta. This notice never waits for approval or stalls automated review.
- Preserve current email and Slack threads, language selection, task activity trail, failure handling, and quality/merge gates.

## Capabilities

### New Capabilities

- `lifecycle-communication`: Milestone visuals, proposal review package and revision digest, decision cards, verification/PR/feedback summaries, and evidence index across email and Slack.
- `architectural-decision-report`: High-signal, evidence-backed, nonblocking architectural decisions and assumptions report on PR opening and material review updates.

### Modified Capabilities

None. Existing quality and review gates stay authoritative; this change adds presentation and notification behavior around them.

## Impact

- `src/main.py` phase transitions, proposal/revision handoffs, verification results, PR creation/finalization, feedback pushes, task reset/hold/resume state; `src/conversation.py`, `src/gmail_client.py`, and `src/slack_client.py` for channel-appropriate image/file presentation; `src/prompts.py` for bounded structured report generation; reusable rendering/report modules and static milestone assets.
- Generated proposal HTML and version snapshots live under git-ignored `data/`, never inside the active or archived target-repo change. No new service or interactive Slack permissions are required. Gmail attachment cap and existing Slack upload behavior remain applicable.
- Unit and integration tests for both transports, revision cycles, review timing, evidence provenance, and restart-safe milestone/report sends; update README with the user-visible message flow.
