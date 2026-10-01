## MODIFIED Requirements

### Requirement: Task milestones are announced with visual progress
Codebot SHALL announce important results, blockers and decisions in concise accessible text in the task conversation, carrying reached milestone information in those messages when useful. It SHALL NOT produce standalone routine phase announcements, progress images or periodic working check-ins. Retries and resumption SHALL NOT repeat unchanged announcements. A confirmed external merge SHALL count as a merge; completion or abort without a confirmed merge SHALL NOT. Default waiting reminders SHALL consist of at most one concise reminder after 24 hours per unchanged pending decision, without quoting the previous full message or resending its attachments.

#### Scenario: Normal lifecycle
- **WHEN** a task progresses through exploration, planning, implementation, verification and archival
- **THEN** codebot sends important results and decision handoffs without separate routine phase images or working check-ins

#### Scenario: Repeated work without a new milestone
- **WHEN** verification retries, a PR gets re-reviewed, or a held task resumes at the same milestone
- **THEN** codebot does not repeat an unchanged milestone notice solely because of retry or resumption

#### Scenario: Unrelated message
- **WHEN** codebot answers STATUS, asks a question or sends a reminder
- **THEN** no progress image or full previous message is appended

#### Scenario: Completion without merge
- **WHEN** the user marks a task complete or aborts it without a confirmed PR merge
- **THEN** codebot does not announce a merge

#### Scenario: Pending decision reminder
- **WHEN** a decision has remained unanswered and unchanged for 24 hours
- **THEN** codebot sends one short self-contained reminder stating the decision and valid response, without repeating the full original message

### Requirement: Decision-first messages
Messages requiring approval, an answer or a PR decision SHALL begin with the concrete decision, valid responses and what happens next. Operational blockers SHALL identify the actual unresolved cause and who acts next, not merely ask for generic guidance. Commands SHALL be described consistently with their actual scope and behavior, including the distinction between `merge` and `merge anyway`. Ordinary messages SHALL target 6–10 lines and place extensive technical detail in attachments or linked reports. Fixed operational copy SHALL use the task language with bounded localization that cannot block coding or delivery for an agent-length timeout.

#### Scenario: Reviewing a proposal
- **WHEN** codebot requests proposal approval
- **THEN** it starts with the approval decision and revised scope when applicable, and identifies the attached complete package

#### Scenario: Asking a question
- **WHEN** a coding or recovery turn requires user input
- **THEN** the message asks the specific unresolved question and explains the consequence without treating the answer as whole-task approval

#### Scenario: Comments prevent merge
- **WHEN** unresolved comments block ordinary merge
- **THEN** the message does not advertise `merge` as a command that bypasses those comments

### Requirement: Human-readable implementation handoffs
Before human PR review, codebot SHALL summarize current snapshot-bound requirement coverage and actual OpenSpec, checks, internal review and applicable E2E outcomes. Skipped, waived, unavailable, indeterminate, infrastructure and confirmed preexisting outcomes SHALL remain distinguishable from passed checks. The handoff SHALL lead with task/PR links, principal implemented changes and next action, and index confirmed evidence and detailed attached reports. It SHALL NOT reuse obsolete progress narration as the delivery summary. Feedback updates SHALL map requests to delivered changes, verification and remaining decisions.

#### Scenario: Repository without an e2e harness
- **WHEN** codebot delivers a repository without an E2E harness
- **THEN** E2E is labeled not applicable, not passed, and no evidence is invented

#### Scenario: Feedback applied and pushed
- **WHEN** requested changes are pushed
- **THEN** the update maps feedback to current changes, coverage and available verification/evidence

#### Scenario: Evidence unavailable
- **WHEN** recording or delivery fails
- **THEN** codebot describes its actual availability and does not claim a file is attached without confirmation

#### Scenario: Historical summary contradicts current PR
- **WHEN** an earlier agent summary says no PR or push exists but the current PR has been published
- **THEN** the delivery is built from current facts and omits that obsolete narration

## ADDED Requirements

### Requirement: Status reflects real activity and contact
STATUS SHALL report the current task, activity, next step, last effective progress and any pending user decision without starting a coding turn. Task-thread STATUS and KICK requests and their responses SHALL update task contact bookkeeping safely. A long-open phase without live activity SHALL NOT be described as active work solely because its state name denotes work.

#### Scenario: STATUS after a quiet period
- **WHEN** the user requests STATUS on the task thread and codebot responds
- **THEN** a subsequent reminder does not claim the thread has been quiet since before that exchange

#### Scenario: Stalled phase
- **WHEN** a work phase has no active execution and no recent effective progress
- **THEN** STATUS identifies the last activity and waiting or retry condition rather than claiming continuous work
