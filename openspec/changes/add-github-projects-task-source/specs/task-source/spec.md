## Purpose

Defines how codebot selects the backend that holds its backlog (a Google Doc or a
GitHub Projects v2 board), the item contract every backend implements for the
orchestrator, and the GitHub backend's semantics for picking, claiming, holding,
completing and seeding tasks and for linking the resulting pull request.

## ADDED Requirements

### Requirement: Task source selection
Codebot SHALL read the backlog through a single task-source interface and
select the backend from `CODEBOT_TASK_SOURCE`, accepting `gdoc` (the default)
and `github`. Any other value SHALL stop startup with a message naming the
accepted values. In `gdoc` mode `CODEBOT_DOC_ID` SHALL be required; in `github`
mode the project owner and number SHALL be required (given directly or as the
project URL) and `CODEBOT_DOC_ID` SHALL NOT be.

#### Scenario: Default keeps the Google Doc
- **WHEN** `CODEBOT_TASK_SOURCE` is unset and `CODEBOT_DOC_ID` is set
- **THEN** codebot starts and works the Google Doc exactly as before

#### Scenario: GitHub selected without a project
- **WHEN** `CODEBOT_TASK_SOURCE=github` and no project owner/number or URL is set
- **THEN** startup stops with a message naming the missing setting

### Requirement: Backend-neutral item contract
Every backend SHALL expose the same operations — list pending items, claim,
unclaim, hold, unhold, mark done, ensure an item exists, note the pull request —
and SHALL return pending items as records carrying the item text, its detail,
local image paths, whether this instance already claimed it, its `Codebot[n]`
priority, and a backend identity (`id`, empty for the Doc). Codebot SHALL carry
the identity alongside the text for the life of the task, including through
HOLD/CONTINUE, and every backend SHALL accept identity-less calls by matching on
text.

#### Scenario: Identity survives a hold
- **WHEN** a task with a backend identity is put on hold and later resumed
- **THEN** the unhold and re-claim calls receive that identity

### Requirement: GitHub pending items
In `github` mode a project item SHALL be pending when its content is an issue in
the target repository, its Status is one of `CODEBOT_GH_PROJECT_PICK_STATUSES`
(default `Ready`), and it carries no claim or hold label of any instance. Items
in the active status carrying THIS instance's claim label SHALL also be listed,
flagged as already claimed, so a lost state file resumes them. Draft cards, pull
requests and issues from other repositories SHALL be skipped and their count
logged. The issue title is the item text and the issue body is its detail; images
referenced in the body are downloaded best-effort.

#### Scenario: Ready issue is offered
- **WHEN** an issue from the target repo sits in `Ready` with no codebot label
- **THEN** it is listed as pending

#### Scenario: Backlog column and foreign claims are hidden
- **WHEN** an issue sits in `Backlog`, or in `Ready` with another instance's
  claim label
- **THEN** it is not listed

### Requirement: GitHub claim, hold and completion
Claiming SHALL add the `codebot:<instance>` label, re-read the issue, refuse
(removing its own label) when another instance's claim label is present, and
only then move the item to `In progress`. Holding SHALL replace the claim label
with `codebot-hold:<instance>` without changing the status; unholding SHALL
remove it. Unclaiming SHALL remove the claim label and return the item to the
first pick status. Marking done SHALL move the item to `Done` and remove this
instance's labels; an item already in `Done` SHALL count as success.

#### Scenario: Lost claim race
- **WHEN** two instances add their claim labels to the same issue before either
  re-reads it
- **THEN** each sees the other's label, removes its own and reports the claim as
  lost, and neither moves the item to `In progress`

#### Scenario: Merge completes the item
- **WHEN** the pull request merges or the user sends DONE
- **THEN** the item moves to `Done` and the instance's labels are removed

### Requirement: GitHub pull-request linking
When a pull request is opened for a GitHub-sourced task, codebot SHALL include
`Closes <issue url>` in the PR body and move the item to `In review`; the PR
link reaches the issue through the activity trail. Failure of the write-back
SHALL be logged and SHALL NOT block the pull request flow.

#### Scenario: PR opened
- **WHEN** `do_open_pr` obtains the PR URL for a task with an issue URL
- **THEN** the PR body references the issue, the item is in `In review`, and the
  trail carries a "PR opened" note with the URL

### Requirement: Activity trail on the item
Codebot SHALL post a note on the backlog item at every task milestone — the
pick and branch, every message emailed to the user (proposal, questions, PR
ready, hold, resume, abort, stuck, completion) with its body, the user's
approval and answers, implementation complete, verification and internal
review passed, each e2e result, archive done, PR opened, each review round,
conflicts resolved, and merge — prefixed with the instance name. Every backend
SHALL implement one operation, `note_activity(text, id, message, ref)`,
returning an opaque thread reference that codebot passes back on later notes.
A failure to post SHALL be logged and SHALL NOT change the task's state.
`CODEBOT_ACTIVITY_TRAIL=off` SHALL disable the trail.

#### Scenario: GitHub note
- **WHEN** a milestone occurs for a GitHub-sourced task
- **THEN** a comment with the note appears on the task's issue

#### Scenario: Google Doc thread per task
- **WHEN** the first note of a task is posted on a Doc-sourced task
- **THEN** a doc-level comment quoting the item text is created, and later notes
  of the same task are replies in that comment thread

#### Scenario: Tracker failure
- **WHEN** posting a note raises (for example the Doc token lacks the Drive scope)
- **THEN** the error is logged with guidance and the task proceeds unchanged

### Requirement: GitHub self-healing seeding
`ensure_item` in `github` mode SHALL create an issue in the target repository,
add it to the project and place it in the first pick status, unless an item
whose title or first body line matches the text already exists on the board in
any status.

#### Scenario: Seed once
- **WHEN** the same missing-infrastructure text is ensured on two consecutive picks
- **THEN** exactly one issue is created

### Requirement: GitHub startup validation
At startup in `github` mode codebot SHALL resolve the project, verify that every
configured status name exists among the Status options (listing the actual
options on failure), ensure this instance's claim and hold labels exist in the
target repository, and translate a token-scope error into a message that names
the `project` scope.

#### Scenario: Token lacks project scope
- **WHEN** `GH_TOKEN` cannot read the project
- **THEN** startup stops with a message that mentions the `project` scope
