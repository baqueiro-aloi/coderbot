## Purpose

Ensure product feedback is investigated and incorporated durably, with revised approval when it changes material requirements or invalidates the approved design.

## ADDED Requirements

### Requirement: Feedback is durable and prioritized
Codebot SHALL record authorized task-thread feedback with its original text, identity, receipt time and handling outcome before acknowledging or consuming it. It SHALL attend pending feedback before initiating further automated review or conflict work. During an active turn it SHALL acknowledge and queue feedback for the next safe boundary without starting a concurrent coding turn. Pending feedback SHALL survive restart, hold, phase transitions and technical retries.

#### Scenario: Feedback during automated review
- **WHEN** the user reports a missing selector while review threads are pending
- **THEN** codebot investigates that feedback before beginning another automated repair round

#### Scenario: Restart after receipt
- **WHEN** codebot restarts after acknowledging but before handling feedback
- **THEN** the original feedback remains pending and is handled once

### Requirement: Questions and requirements are investigated together
Codebot SHALL distinguish informational questions, localized corrections, material changes and unresolved product ambiguity using the approved artifacts and actual implementation. A question containing a requirement assertion SHALL NOT be dismissed as unclear merely because it is phrased as a question. It SHALL answer the factual question and record the disposition of the asserted requirement.

#### Scenario: Missing dropdown question
- **WHEN** the user says “No veo un drop down donde se pueda elegir el modelo. Eso está implementado? Eso es parte de feature”
- **THEN** codebot verifies whether selection exists and satisfies the approved feature and explains the finding rather than ignoring the message or asking for a command keyword

### Requirement: Material feedback reopens planning
An important omitted requirement, scope change, architectural change or invalidated assumption SHALL cause codebot to revise proposal, design, specifications and tasks and request approval of that revision before continuing implementation. Localized corrections consistent with the approved design SHALL be repaired without a new proposal. Materiality SHALL depend on behavior and product impact rather than code size alone.

#### Scenario: Selector requires design changes
- **WHEN** investigation confirms a missing model selector requires material session, provider or protocol behavior changes
- **THEN** codebot enters revised planning and awaits explicit approval before implementing those changes

#### Scenario: Localized defect
- **WHEN** feedback identifies a typo or a localized defect with an unambiguous approved behavior
- **THEN** codebot corrects and verifies it without requiring proposal reapproval

### Requirement: Replanning preserves legitimate work and versions consent
Codebot SHALL preserve valid implementation and Git history during replanning, retain the task and existing PR linkage, and suspend incompatible autonomous actions and merge. It SHALL bind approval and merge instructions to the reviewed version and reject superseded consent. An archived change SHALL receive a linked complementary change instead of rewriting the historical archive; the revised review package SHALL identify the relationship and retained work. Revised implementation SHALL update affected verification and feature demonstrations.

#### Scenario: Feedback after PR publication
- **WHEN** material feedback arrives after archival and PR publication
- **THEN** codebot retains the PR and implementation, prepares a linked complementary proposal and does not apply an earlier merge instruction to the revised content

#### Scenario: Planning cleanup
- **WHEN** codebot revises a proposal after legitimate implementation
- **THEN** planning cleanup does not undo the implementation as premature work
