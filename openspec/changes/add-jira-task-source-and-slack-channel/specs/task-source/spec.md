## Purpose

Defines a common backlog contract and Jira Cloud issue lifecycle so Coderbot can work a selected project's tasks with the same ownership and completion behavior as its existing sources.

## ADDED Requirements

### Requirement: Independent Jira task-source selection
Coderbot SHALL accept `jira` as a task source in addition to `gdoc` and `github`, while selecting its communication channel independently. Jira mode SHALL require a Jira Cloud site, project key, account email, API token, and configured workflow statuses; other modes SHALL NOT require Jira credentials. Unset task source SHALL continue to select `gdoc`.

#### Scenario: Jira with email
- **WHEN** Jira is selected as the task source and email as the communication channel
- **THEN** Coderbot works Jira issues and carries out the existing email conversation

#### Scenario: Existing default
- **WHEN** neither selector is configured and the Google Doc configuration is valid
- **THEN** Coderbot uses the Google Doc and email

### Requirement: Jira pending issue discovery
Coderbot SHALL list issues from the configured Jira Cloud project whose workflow status is the configured eligible status, excluding issues claimed or held by another instance. An issue already claimed by this instance and not done SHALL also be recoverable when local task state is lost. Each candidate SHALL include its stable Jira issue identity, key, summary, description, browser URL, and `Codebot[n]` priority if present; issue screenshots and image attachments referenced by its description SHALL be made available to exploration when accessible. The project board's column configuration SHALL NOT change eligibility.

#### Scenario: Eligible issue on a grouped board
- **WHEN** an unclaimed issue is in the configured eligible workflow status but its board column groups it with other statuses
- **THEN** the issue is offered as a task regardless of the board's grouping

#### Scenario: Issue claimed elsewhere
- **WHEN** an otherwise eligible issue carries another instance's claim or hold label
- **THEN** it is not offered to this instance

#### Scenario: Recovered own claim
- **WHEN** local state is lost but an unfinished issue retains this instance's claim label
- **THEN** Coderbot offers the issue for recovery before an unrelated task

### Requirement: Jira issue ownership and configurable lifecycle
Coderbot SHALL use an issue label containing its readable instance name and persistent ownership fingerprint to claim a Jira task, re-read the issue after adding its label, and refuse the claim and remove only its own label if it observes another fingerprint's claim. It SHALL transition claimed issues to the configured active workflow status, PR-open issues to the configured review status, and merged or explicitly DONE issues to the configured done status. ABORT SHALL remove its claim and restore the configured eligible status; HOLD SHALL retain exclusive ownership with a similarly fingerprinted hold label until CONTINUE restores its claim. It SHALL preserve unrelated labels and SHALL NOT mark an issue done merely because a PR was opened.

#### Scenario: Concurrent claims are observed
- **WHEN** two instances' claim labels are visible during post-claim verification
- **THEN** each detecting the competing label backs off without intentionally advancing the issue's status

#### Scenario: PR is awaiting merge
- **WHEN** a PR is opened for a claimed Jira issue
- **THEN** the issue enters the configured review status and retains the instance's ownership label until the task finishes

#### Scenario: PR merged or DONE
- **WHEN** Coderbot detects a merged PR or accepts DONE for the Jira task
- **THEN** it transitions the issue to the configured done status and removes its claim or hold label

#### Scenario: Hold and abort
- **WHEN** a Jira task is held and later continued, or is aborted
- **THEN** HOLD prevents other instances from picking it, CONTINUE restores ownership, and ABORT releases it to the configured eligible status

### Requirement: Jira issue details, seeding and activity trail
Jira issue descriptions and notes SHALL preserve meaningful text and links when converting between Jira's rich-text format and Coderbot's task text. Coderbot SHALL post lifecycle milestones and user-facing message bodies as issue comments when the activity trail is enabled; a failed note SHALL be logged without blocking task progression. Self-healing backlog items SHALL be created as Jira issues in the configured project and eligible status only when no equivalent item already exists, including completed items.

#### Scenario: Issue contains rich description
- **WHEN** a Jira issue description contains paragraphs, lists and links
- **THEN** Coderbot presents their readable contents to the coding agent instead of raw rich-text JSON

#### Scenario: Missing infrastructure item already exists
- **WHEN** an equivalent Jira issue already tracks a missing test harness, regardless of status
- **THEN** Coderbot does not create a second issue

#### Scenario: Milestone comment fails
- **WHEN** posting a Jira activity comment fails
- **THEN** Coderbot logs the failure and continues the task

### Requirement: Jira PR reference without premature completion
For a Jira-sourced task Coderbot SHALL include the Jira issue key and browser URL in the GitHub PR body, including a human-readable `Closes <Jira key>` reference. It SHALL also record the PR URL on the Jira issue. That text SHALL NOT substitute for an explicit Jira transition after merge or DONE. For a GitHub-sourced task, GitHub's existing closing reference SHALL retain its current behavior.

#### Scenario: Jira PR created
- **WHEN** Coderbot opens a PR for Jira issue `PROJ-123`
- **THEN** the PR body identifies `Closes PROJ-123` and links the issue, the issue records the PR URL, and the issue remains open in review until completion

### Requirement: Jira startup checks
In Jira mode Coderbot SHALL validate authentication, access to the configured project, ability to read issues and the configured eligible/active/review/done statuses, and report actionable errors instead of silently starting with an empty backlog.

#### Scenario: Invalid configured status
- **WHEN** a configured Jira workflow status is unavailable for the project
- **THEN** startup reports which status is invalid
