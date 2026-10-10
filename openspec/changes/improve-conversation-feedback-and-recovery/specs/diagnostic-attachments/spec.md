## Purpose

Keep operational messages readable while delivering complete, durable incident diagnostics as reliably tracked attachments in every supported communication channel.

## ADDED Requirements

### Requirement: Complete incident diagnostics
For every notified execution error or blocker with technical diagnostics, codebot SHALL preserve a UTF-8 report containing the complete available traceback and exception chain, original error, incident identity, task, phase and timestamp, and available command, exit code and relevant stdout/stderr. It SHALL redact credentials and tokens while retaining diagnostic structure. Reports SHALL be durable and referenced by task and attempt; failed executions SHALL NOT make diagnostic artifacts ineligible for delivery. Raw technical diagnostics SHALL NOT be translated or truncated to a fixed message excerpt.

#### Scenario: Long traceback
- **WHEN** an exception traceback exceeds 2000 characters
- **THEN** the report preserves its complete redacted contents and the outgoing body contains a short explanation rather than the traceback

#### Scenario: Silent retries
- **WHEN** an execution failure is retried without a user notification
- **THEN** its diagnostics are retained and are available in the corresponding incident attachment if the incident is later notified

### Requirement: Channel-neutral attachment delivery
All communication adapters SHALL support diagnostic attachments through a common contract specifying stable artifact identity, filename, media type and size and reporting delivery outcome per artifact. Email and Slack SHALL deliver real downloadable files. Future adapters SHALL satisfy the same contract. Existing proposal and evidence attachments SHALL remain supported. Reports exceeding a channel limit SHALL be losslessly compressed or split into labeled attached parts instead of silently omitted or pasted into the message body.

#### Scenario: Same report in both supported channels
- **WHEN** the same diagnostic artifact is sent by Email or Slack
- **THEN** each recipient receives a downloadable file with the complete diagnostic content and matching identity

#### Scenario: Oversized report
- **WHEN** a diagnostic exceeds the adapter's attachment limit
- **THEN** codebot delivers compressed or numbered parts that reconstruct the complete report

### Requirement: Attachment failures are independently retryable
Codebot SHALL record pending, confirmed and failed attachment deliveries and retry pending files independently from coding work and confirmed message/file delivery. It SHALL NOT advertise an attachment as delivered without confirmation. A file upload failure SHALL NOT restart the phase or resend confirmed attachments. Restart reconciliation SHALL retain pending delivery and distinguish uncertain from confirmed sends. Reminder messages SHALL NOT repeatedly upload previously confirmed diagnostics.

#### Scenario: Slack upload fails
- **WHEN** Slack accepts the short notification but rejects its diagnostic upload
- **THEN** codebot records the failed attachment, reports its pending status truthfully and retries the file without rerunning the agent or duplicating confirmed artifacts

#### Scenario: Restart with pending delivery
- **WHEN** codebot restarts between diagnostic generation and delivery confirmation
- **THEN** it resumes or reconciles that delivery using the same artifact identity

### Requirement: Diagnostics cover all operational error routes
Agent execution, quality checks, recovery, Git/PR operations and archival notifications SHALL use the diagnostic attachment mechanism. Relevant existing check output files SHALL be attached or indexed in the report without dumping serialized test results into conversation text. Operational summaries SHALL state the issue, owner of the next action and specific next step.

#### Scenario: E2E indeterminate
- **WHEN** final E2E validation is indeterminate with lengthy test diagnostics
- **THEN** codebot describes the unknown outcome and its next diagnostic step briefly and supplies the details as attachments
