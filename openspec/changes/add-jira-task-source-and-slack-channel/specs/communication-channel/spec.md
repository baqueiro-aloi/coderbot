## Purpose

Defines how Coderbot exchanges task updates, user decisions, commands, check-ins and evidence over independently selected email or Slack conversations, and how users configure the full deployment interactively.

## ADDED Requirements

### Requirement: Independent conversation channel selection
Coderbot SHALL select email or Slack independently of its task source. Email SHALL remain the default, preserving existing Gmail thread and command behavior. Slack mode SHALL require a configured public channel and credentials for this instance's Slack app and SHALL NOT require a user email; an invalid channel or credentials SHALL prevent starting Slack mode with an actionable error.

#### Scenario: Google Doc over Slack
- **WHEN** the Google Doc task source and Slack conversation channel are configured
- **THEN** Coderbot works Google Doc items while conducting task conversations in Slack

#### Scenario: Jira over email
- **WHEN** the Jira task source and email channel are configured
- **THEN** Coderbot works Jira issues while using existing email conversations

### Requirement: Pre-task dirty checkout in Slack mode
When Slack is selected and the target checkout is dirty before a task can be claimed, Coderbot SHALL notify the configured channel once for that blocked episode without treating the announcement or replies to it as a task thread. It SHALL recheck the checkout on subsequent ticks and resume picking automatically once clean, without requiring a user reply. User-authored top-level messages and replies outside owned task threads SHALL still not be commands. In email mode the existing WAIT_CLEAN reply workflow SHALL remain unchanged.

#### Scenario: Dirty checkout becomes clean
- **WHEN** a Slack-enabled bot cannot pick because the checkout is dirty and the user subsequently cleans it
- **THEN** the bot announces the block only once and retries picking automatically on the next tick after the checkout becomes clean

#### Scenario: Reply to operational announcement
- **WHEN** someone replies ABORT to the dirty-checkout announcement outside a task thread
- **THEN** Coderbot ignores it as a command

### Requirement: Complete interactive setup
Coderbot SHALL offer an interactive terminal configuration UI usable on macOS and Linux when launched from either bash or zsh. It SHALL open with a menu of independently editable sections for repository, backlog, conversation, agent, evidence and advanced settings. Each section SHALL display a masked preview of its pending changes and offer `Test` and `Save and Close`. `Test` SHALL check that section and any required previously saved dependencies, with actionable, integration-specific errors; `Save and Close` SHALL run the same test, persist the section's changes only on success, return to the menu and mark the section complete. A menu-level `Test` SHALL validate the entire configured installation. Changing a saved dependency SHALL invalidate affected completion checkmarks until those sections are tested again. `Exit` SHALL leave no unsaved edits. The UI SHALL make every effective user-configurable runtime setting available, including settings introduced with Jira and Slack and settings that previously required manual `.env` edits. A usable menu-driven text-mode setup SHALL remain available without TUI support or when the terminal is non-interactive. It SHALL NOT require credentials for integrations that were not selected.

#### Scenario: Menu and section save
- **WHEN** the user opens setup, edits the repository section and clicks `Save and Close`
- **THEN** setup tests repository settings, writes only those changes to `.env`, returns to the main menu and marks Repository complete without requiring unfinished Jira, Slack or agent settings

#### Scenario: Section test fails
- **WHEN** a user tests a Slack configuration whose bot has not joined the selected public channel
- **THEN** setup stays in Conversation, explains how to invite that specific bot or correct its token and does not overwrite `.env` or mark the section complete

#### Scenario: Test full installation
- **WHEN** the user selects `Test` from the main menu
- **THEN** setup validates all selected sections and their cross-section dependencies and displays actionable problems without saving pending values

#### Scenario: Leave menu without pending edits
- **WHEN** the user has completed or skipped sections and selects `Exit` from the main menu
- **THEN** setup exits with only the sections already saved to `.env` and no undisclosed draft changes

#### Scenario: Jira and Slack first-time setup
- **WHEN** a user chooses Jira as the task source and Slack as the communication channel
- **THEN** setup guides them through Jira site/project/account API token and workflow statuses, separate Slack bot/app tokens and public channel, and the independently required GitHub and evidence settings without asking for a Gmail address

#### Scenario: Slack token acquisition and channel selection
- **WHEN** Slack is selected as the conversation channel
- **THEN** setup explains where to create a bot (`xoxb-`) token and a Socket Mode app-level (`xapp-`) token for this instance, provides links that open the appropriate Slack app settings, requests both tokens before the channel ID, and lists this bot's joined public channels by name for selection while storing the chosen channel ID

#### Scenario: Slack access error names the cause
- **WHEN** Slack reports `missing_scope`, an unjoined channel, a private channel, or an invalid bot/app token
- **THEN** setup distinguishes the cause and names the exact permission, invitation or token action needed; it SHALL NOT claim that a scope is missing when only channel membership is missing

#### Scenario: Slack credentials cannot list usable channels
- **WHEN** the bot token lacks channel access, the app token cannot open Socket Mode, or the app has joined no public channels
- **THEN** setup shows an actionable explanation and lets the user correct the tokens, invite the bot to a public channel, and retry without writing `.env` or requiring the user to guess an ID

#### Scenario: Existing channel after token change
- **WHEN** a user changes either Slack token during reconfiguration
- **THEN** setup reloads joined public channels from the new app before allowing a channel choice; an old channel ID that the new bot cannot access is not silently retained

#### Scenario: GitHub Projects board after GitHub token
- **WHEN** GitHub Projects is selected and a GitHub token and target repo are configured
- **THEN** setup lists accessible Projects v2 boards for the relevant owner and offers their URLs by title, while allowing an explicitly entered URL when a different owner is required

#### Scenario: Advanced settings are editable
- **WHEN** a user wants to change any supported runtime environment setting, including GitHub Projects statuses, activity trail, fallback models, retries, evidence or heartbeat tuning
- **THEN** setup offers the setting in an advanced view with its effective default and validation, rather than requiring a manual `.env` edit

#### Scenario: Text-mode portability
- **WHEN** setup runs on macOS or Linux under bash or zsh without a compatible interactive terminal
- **THEN** the user can still complete configuration through an accessible text-mode flow

### Requirement: Safe reconfiguration and coverage of runtime settings
When an existing `.env` is reviewed, setup SHALL preserve all settings that the user did not explicitly change, including unknown keys, inactive integration settings, and legacy aliases; it SHALL mask secret values in displays and backups SHALL be created before replacement. Canceling before confirmation SHALL leave the file unchanged. Changes SHALL be applied only after reviewing the resulting non-secret configuration, and a failed validation SHALL keep the prior working file. The repository SHALL check that newly introduced runtime configuration is documented and offered by setup so omissions are detected before release.

#### Scenario: Existing advanced and unknown values
- **WHEN** a user opens setup on an existing `.env` with advanced or unfamiliar keys, edits only the Slack channel and confirms
- **THEN** all untouched settings and comments remain present and the file is backed up before the new value is written

#### Scenario: Canceled or invalid setup
- **WHEN** a user cancels or a new configuration fails validation
- **THEN** the prior `.env` stays intact and no secret values are shown in terminal output

#### Scenario: New configuration added to runtime
- **WHEN** a new runtime environment setting is added without being documented and exposed in interactive setup
- **THEN** the repository's configuration-coverage check fails

### Requirement: One Slack thread per task
After successfully claiming a task, Coderbot SHALL post one root message in the configured public Slack channel identifying the task, its source URL where available, and its instance. It SHALL persist that message's channel and root timestamp and send task updates, approval requests, questions, check-ins, STATUS responses, PR links, completion reports, and replies in its thread. A held task SHALL retain its thread across unrelated tasks and process CONTINUE in that same thread. Recovering from restart SHALL continue an existing thread instead of opening a duplicate when its root is already known.

#### Scenario: Claimed task begins
- **WHEN** Coderbot claims a task and Slack is selected
- **THEN** it creates a root message and sends later task communication as replies to that message

#### Scenario: Held task resumes
- **WHEN** a user posts CONTINUE in the thread of a held task
- **THEN** that task is queued to resume with its original thread after the current work permits

### Requirement: Slack event intake and durable processing
Coderbot SHALL receive messages in Slack via Socket Mode for its own per-instance app, acknowledge events promptly, ignore its own bot messages, and only process messages from the configured channel in a thread Coderbot owns (active or held). Accepted events SHALL survive a restart after acknowledgment, be deduplicated, and be applied in thread order once the current agent turn finishes; message delivery SHALL NOT interrupt the running agent turn. Events for other instances' threads and top-level messages from users SHALL NOT become task replies or commands.

#### Scenario: Reply arrives during a long agent turn
- **WHEN** a member replies in an owned thread while the coding agent is running
- **THEN** Coderbot records the reply without interrupting the agent and handles it after that turn finishes

#### Scenario: Unrelated channel message
- **WHEN** a member posts ABORT as a new top-level message or replies in another bot's thread
- **THEN** this instance does not treat it as a command or a task answer

#### Scenario: Retry and restart
- **WHEN** Slack redelivers an event, or the process restarts after acknowledging an accepted reply
- **THEN** that reply is handled once and is not lost

### Requirement: Slack thread commands and decisions
Any human member of the configured public channel SHALL be permitted to reply in an owned thread with the existing ABORT, STATUS, DONE, HOLD/PAUSE and CONTINUE/RESUME commands. Thread-scoped commands SHALL affect the task represented by that thread rather than a different active task; STATUS SHALL report on that task in its thread. Task approvals, questions, PR feedback, merge decisions and stuck recovery SHALL accept replies from any human member in that owned thread. Top-level posts SHALL NOT trigger commands, even when they mention a bot or an instance name. A bare DONE reply on the active task thread SHALL retain the current distinction from an explicitly targeted DONE command.

#### Scenario: Authorized by thread location
- **WHEN** any human channel member sends HOLD as a reply to this instance's active task thread
- **THEN** Coderbot holds that task and confirms in its thread

#### Scenario: Bare DONE on active thread
- **WHEN** a user replies DONE without targeting an instance in the active task thread
- **THEN** it is evaluated as a conversational answer rather than an unconditional completion command

#### Scenario: STATUS on a held thread
- **WHEN** a user replies STATUS to a held task thread
- **THEN** Coderbot responds in that thread with the task's held status and instance identity

#### Scenario: ABORT on a held thread while another task is active
- **WHEN** a user replies ABORT to a held task thread while this instance works another task
- **THEN** Coderbot releases the held task and leaves the unrelated active task in progress

### Requirement: Slack delivery of evidence and long messages
For Slack tasks Coderbot SHALL share available screenshots and reports in the task thread and link large evidence videos uploaded to Google Drive there. Slack message length or file-upload constraints SHALL NOT silently truncate a proposal, review summary, question or evidence handoff: longer content SHALL be split or otherwise shared accessibly in the thread, and unavailable evidence SHALL be reported without blocking PR review.

#### Scenario: Video evidence is available
- **WHEN** a PR-ready handoff includes a large Playwright video in Slack mode
- **THEN** the task thread contains its Google Drive link

#### Scenario: Long proposal
- **WHEN** a proposal is too long for a single Slack message
- **THEN** the user receives its complete contents within the task thread

### Requirement: Stale Slack reply protection
When a PR is materially changed by conflict resolution, Coderbot SHALL set aside earlier unhandled Slack replies to the prior PR version, especially merge decisions, and ask for a fresh instruction in the same task thread.

#### Scenario: Merge instruction predates conflict resolution
- **WHEN** a merge reply arrived before Coderbot updated a conflicting PR
- **THEN** that reply is not used to merge the updated PR and the user is asked to reconsider it
