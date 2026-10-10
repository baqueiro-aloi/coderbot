## Purpose

Surfaces important architectural choices actually present in a new pull request, so reviewers can inspect consequential implementation assumptions without adding another approval gate.

## ADDED Requirements

### Requirement: Early informational architectural report
After opening a PR, codebot SHALL send a separate informational message in the task thread during the automated-review wait, before the PR-ready human handoff when such a wait exists. It SHALL identify a short, prioritized set of high-impact architecture decisions and unresolved assumptions evidenced by the implementation, including consequential infrastructure, data boundaries, privileges, service boundaries, external dependencies and difficult-to-reverse choices. Each reported item SHALL identify its impact, whether it was already described in approved OpenSpec artifacts or is newly introduced, and a reference to actual changed source/configuration files. Codebot SHALL distinguish an implemented decision from an assumption whose premise remains unverified; it SHALL NOT assert an impact unsupported by available evidence.

#### Scenario: New infrastructure choice
- **WHEN** implementation adds a separate managed database not specified in the approved change
- **THEN** the report highlights that choice, its impact and the relevant PR files, marking it as not previously specified

#### Scenario: Container privilege change
- **WHEN** implementation adds a container privilege such as `SYS_ADMIN` or a `security_opt`
- **THEN** the report highlights the change and points to the changed configuration instead of burying it in a generic feature summary

#### Scenario: No significant decision found
- **WHEN** the implementation contains no supported high-impact architectural choice beyond the approved design
- **THEN** codebot communicates that no additional significant decisions were identified without inventing list items

### Requirement: Report does not gate the lifecycle
Sending or producing the architectural report SHALL NOT add an approval wait, suppress automated review, or change verification and PR merge rules. When report generation or delivery fails, codebot SHALL log the failure and continue the normal PR lifecycle; it SHALL NOT represent an unavailable analysis as a confirmed absence of decisions. For repos without an automated-review workflow, codebot SHALL send the report at PR opening before or alongside the immediate PR-ready handoff, without inserting a wait.

#### Scenario: Automated reviewer running
- **WHEN** a PR opens and the Code Review workflow is present
- **THEN** the architectural notice is sent while review proceeds, and the bot continues polling and addressing review comments normally

#### Scenario: Report unavailable
- **WHEN** architectural analysis fails after a PR was opened
- **THEN** automated review and eventual PR-ready handoff continue, and no unsupported "no significant decisions" claim is sent

### Requirement: Material architectural updates
If review or user feedback changes a previously reported high-impact decision, codebot SHALL send a concise delta identifying the changed decision and the new evidence after the changes are pushed, without resending the unchanged report. Routine code fixes SHALL NOT trigger another architectural notice.

#### Scenario: Review changes the data boundary
- **WHEN** a PR review revision replaces a separate database with a shared instance and pushes the update
- **THEN** the thread receives only the relevant architectural decision update with references to the new PR version
