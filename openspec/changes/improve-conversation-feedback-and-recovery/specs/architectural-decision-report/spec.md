## MODIFIED Requirements

### Requirement: Early informational architectural report
After opening a PR, codebot SHALL generate an evidence-backed prioritized report of consequential implemented architectural choices and unresolved assumptions, identifying impact, approved versus newly introduced decisions and references to changed files. It SHALL distinguish unverified assumptions from implemented facts. Supported important findings SHALL be surfaced concisely during automated review or in the immediate PR handoff when no review wait exists, with full detail attached or linked. No standalone empty report or repeated unchanged finding SHALL be sent.

#### Scenario: New infrastructure choice
- **WHEN** implementation introduces a managed database absent from approved artifacts
- **THEN** the report highlights the choice and impact with references, marking it newly introduced

#### Scenario: Container privilege change
- **WHEN** implementation introduces container privileges
- **THEN** the report identifies the consequential setting and actual changed configuration

#### Scenario: No significant decision found
- **WHEN** analysis finds no supported important decision beyond the approved design
- **THEN** codebot retains the analysis outcome without sending a standalone no-findings notice

### Requirement: Report does not gate the lifecycle
Architectural report generation or delivery SHALL NOT itself add approval waits or suppress review and verification. Failures SHALL be retained as unavailable analysis rather than confirmed absence of decisions, and the lifecycle SHALL continue. Independently established material requirement or design mismatches SHALL follow the replanning policy even if they are also mentioned in the report. Without automated review, findings SHALL be included before or alongside the immediate PR handoff without an additional wait.

#### Scenario: Automated reviewer running
- **WHEN** supported significant findings are delivered during automated review
- **THEN** their delivery alone does not interrupt the review lifecycle

#### Scenario: Report unavailable
- **WHEN** analysis fails after PR publication
- **THEN** the lifecycle continues and codebot does not claim no significant decisions exist

#### Scenario: Material scope mismatch independently confirmed
- **WHEN** investigation establishes a material design mismatch also described in architectural findings
- **THEN** codebot follows replanning because of the mismatch, not because report delivery creates a separate gate
