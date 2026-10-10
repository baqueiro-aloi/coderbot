## Why

Coderbot can work a Google Doc or GitHub Projects backlog, but cannot work a Jira Cloud project's issues; its approval, command, and review conversations require email. Teams using Jira and Slack need the same autonomous lifecycle without changing their project-management or communication tools.

## What Changes

- Add `jira` as an independently selectable task source: discover issues in a configurable eligible Jira workflow status with a configured opt-in label, claim with a separate instance label, transition through configurable active/review/done statuses, keep the activity trail and PR link on the issue, and finish it on merge or DONE.
- Add `slack` as an independently selectable communication channel alongside the existing email default. One public configured channel receives a root message per claimed task; all task messages, replies, commands, status reports, check-ins, and evidence are handled in that thread. Receive messages via Socket Mode without interrupting an in-flight agent turn.
- Give each installation an automatically generated, persistent, readable `codebot-<adjective>-<animal>` name plus a separate persistent ownership fingerprint. Carry both in backlog claim/hold markers to distinguish bots whose readable names coincide, and run a separate Slack app/credential set for each Slack-enabled instance.
- Keep large video evidence on Google Drive; post its link in the selected channel, and deliver other evidence through the selected channel. Keep GitHub PR creation/review unchanged; identify Jira work in the PR body while Coderbot explicitly transitions the Jira issue on merge.
- Replace the linear interactive setup with a terminal menu of independently editable sections on macOS/Linux from bash or zsh. Each section tests its own configuration and dependencies before `Save and Close`, persists its changes immediately, and shows a completion checkmark; a menu-level `Test` checks the whole installation, and `Exit` leaves no pending edits. Ask for credentials before dependent identifiers, fetch accessible Slack channels, Jira projects/workflow statuses and GitHub Projects boards for guided selection, and link to token-creation pages. Preserve untouched `.env` values and keep a usable text-mode path when the TUI is unavailable.
- Audit the setup against all current runtime configuration, update environment documentation, and add coverage that detects settings missing from setup as configuration evolves. Existing Google Doc/GitHub and email deployments retain their defaults.

## Capabilities

### New Capabilities

- `task-source`: Jira Cloud backlog discovery, ownership, state transitions, seeding, issue notes, and PR linkage alongside existing sources.
- `communication-channel`: Independently selected email or Slack transport with task-thread replies, command routing, evidence delivery, Socket Mode reception, and guided configuration of all deployment settings.
- `instance-identity`: Stable, automatically generated, human-readable name and per-installation ownership fingerprint, including compatibility for pre-upgrade claims.

### Modified Capabilities

- `quality-gates`: The PR-ready handoff and kind-aware evidence delivery use the selected communication channel rather than requiring email.

## Impact

- `src/task_source.py`, `src/gdoc_client.py`, `src/github_projects_client.py`, `src/main.py`, `src/config.py`, `src/gmail_client.py`, `src/prompts.py`, `src/evidence.py`/`src/drive_client.py`, and new Jira/Slack integration modules.
- Jira Cloud REST API v3, a Jira account email/API token, one Slack app with bot/app tokens per instance, Slack Web API and Socket Mode, and Google Drive for large evidence videos.
- `scripts/setup.sh` and a host-side terminal UI, OAuth/auth setup guidance, `.env.example`, pinned host-side/runtime dependencies, container/deployment configuration, README, and configuration-inventory plus integration tests.
