## Purpose

Makes every task handoff readable and actionable in both supported conversation channels, while retaining the underlying workflow and complete review artifacts.

## ADDED Requirements

### Requirement: Task milestones are announced with visual progress
Codebot SHALL announce exploration, proposal preparation, proposal awaiting approval, implementation, verification, archiving, PR ready for human review, and confirmed PR merge once per reached milestone in the task conversation. Each announcement SHALL include a compact pre-generated progress image identifying the current milestone and accessible text naming it; email and Slack SHALL receive a reliably viewable representation. Existing messages announcing a milestone SHALL carry that announcement rather than causing a duplicate message. Internal review and optional e2e checks SHALL appear within verification rather than as mandatory separate milestones. An externally merged PR SHALL count as a confirmed merge; marking a task complete without merging SHALL NOT.

#### Scenario: Normal lifecycle
- **WHEN** a task progresses from exploration through proposal, implementation, verification, archival, PR review and a confirmed merge
- **THEN** the task conversation receives one labeled progress announcement for each reached milestone, with the image highlighting the correct position

#### Scenario: Repeated work without a new milestone
- **WHEN** verification retries, a PR gets re-reviewed, or a held task resumes at the same milestone
- **THEN** codebot does not repeat the same milestone announcement solely because of the retry or resumption

#### Scenario: Unrelated message
- **WHEN** codebot sends a question, a silence check-in, or a routine retry/status message
- **THEN** it does not send a new milestone image for that message

#### Scenario: Completion without merge
- **WHEN** the user marks a task complete or aborts it without a confirmed PR merge
- **THEN** codebot does not announce the merge milestone

### Requirement: Complete proposal review document
Whenever codebot requests approval of an initial or revised OpenSpec proposal, it SHALL attach a single offline, self-contained HTML document containing the complete current `proposal.md`, `design.md`, `tasks.md`, and all nested change spec Markdown files. The document SHALL have an interactive left-side index for files and headings with working internal links, readable without network access. It SHALL be derived from the on-disk change, render Markdown safely, and include no working-session transcript or files outside those named artifacts. The review message SHALL retain a brief plain-text summary and explicit approval/change instructions.

#### Scenario: Initial proposal sent
- **WHEN** proposal creation finishes directly or after a question-answer detour
- **THEN** the approval message includes the current complete navigable HTML attachment in the chosen channel

#### Scenario: Revised proposal sent
- **WHEN** the user requests edits to the proposal and codebot sends a new review request
- **THEN** codebot regenerates and attaches the document from the updated on-disk artifacts rather than reusing the prior version

#### Scenario: Unavailable or oversized document
- **WHEN** a required artifact cannot be read or the complete HTML cannot be attached within the channel's limits
- **THEN** codebot reports the missing or undeliverable review package clearly and does not ask the user to approve an incomplete package as if it were complete

### Requirement: Revision summary
For a revised proposal codebot SHALL summarize substantive differences from the preceding sent proposal version, including added, removed and materially changed requirements, design decisions and tasks when present. The summary SHALL reflect actual artifact changes and distinguish an unchanged revision from a material change.

#### Scenario: Proposal revised twice
- **WHEN** two successive review rounds change different OpenSpec artifacts
- **THEN** each outgoing revision summary compares the new document to the version sent immediately before it

### Requirement: Decision-first messages
Messages that require the user's approval, answer, retry guidance or PR decision SHALL begin with a concise description of what is needed, the valid responses and what happens next. This presentation SHALL preserve existing approval/merge classifiers, command scope, language, thread, and permission semantics.

#### Scenario: Reviewing a proposal
- **WHEN** codebot requests proposal approval
- **THEN** the message begins with an explicit approve-or-request-changes decision and links the attached review package

#### Scenario: Asking a question
- **WHEN** the coding session requests user input during a phase
- **THEN** the message foregrounds the concrete question and how to answer without treating an ambiguous answer as whole-task approval

### Requirement: Human-readable implementation handoffs
Before human PR review, codebot SHALL summarize the actual verification outcomes, identifying OpenSpec validation, tests/checks, internal review, and applicable e2e results, with unavailable or skipped checks distinguished from passed checks. Its PR-ready message SHALL lead with a short implementation/review cover note, task/PR links, next action, and a labeled index of the actual available video, report and other evidence, explaining what each demonstrates. After PR feedback is applied, codebot SHALL relate requested changes to delivered changes and verification, without claiming checks it did not perform.

#### Scenario: Repository without an e2e harness
- **WHEN** codebot prepares a PR-ready handoff for a repository without an e2e harness
- **THEN** the verification summary identifies e2e as not applicable rather than passed and the evidence index does not invent an artifact

#### Scenario: Feedback applied and pushed
- **WHEN** the user asks for PR changes and codebot pushes the resulting work
- **THEN** the update maps the request to actual changes and available verification/evidence and links the updated PR

#### Scenario: Evidence unavailable
- **WHEN** recording produces no artifact or a link/upload fails
- **THEN** the handoff explains the missing evidence without advertising an unavailable file or blocking the existing review flow
