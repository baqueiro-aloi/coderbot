## Purpose

Ensure implementation demos are valid, attributable to the delivered implementation, and recoverably published to reviewers without overstating delivery success.

## ADDED Requirements

### Requirement: Retain PR decisions during repairs
The system SHALL durably retain explicit replies to the displayed PR decision received while repairing, pushing or reviewing that same PR, and process them only when its decision becomes actionable. The existing merge gates SHALL remain in effect. Changed PR or displayed decisions SHALL require confirmation; explicit lateral messages SHALL NOT authorize merge.

#### Scenario: Merge anyway during review repairs
- **WHEN** the user replies merge anyway during repairs to a PR with a pending merge decision
- **THEN** the reply waits in the controller queue and reaches the existing merge handler at WAIT_MERGE rather than becoming a lateral conversation

#### Scenario: Different pending decision
- **WHEN** the PR or displayed decision changes before the retained reply becomes actionable
- **THEN** codebot requests confirmation and does not merge using that reply

### Requirement: Separate evidence selection from full-suite verification
The system SHALL distinguish a selected demo run from full-suite verification. Evidence SHALL require passing selected cases without skips, failures, retries or report errors and nonempty current-run videos. Missing matches or a harness validation failure SHALL NOT count as successful evidence. Diagnostics SHALL distinguish capture, validation and conversion failures.

#### Scenario: Filtered demo execution
- **WHEN** only evidence-tagged cases are selected
- **THEN** the selection is validated independently of the full-suite inventory and is not advertised as full-suite verification

#### Scenario: Harness rejects recorded demos
- **WHEN** passing cases generate clips but the harness exits unsuccessfully
- **THEN** diagnostics explain that validation failed after recording, preserve the clips for investigation, and do not publish them as approved evidence

### Requirement: Verified and attributable media
The system SHALL associate reusable evidence with its run, report and implementation snapshot, verify its integrity, and select the requested demo without historical or HTML-report duplicate clips. MP4 delivery SHALL require readable video with positive duration. Unverifiable or outdated artifacts SHALL require recording again rather than publication as current evidence.

#### Scenario: Existing current demo
- **WHEN** a requested demo already has valid current-snapshot provenance
- **THEN** it is reused and converted once without adding duplicate clips

#### Scenario: Invalid or historical artifact
- **WHEN** a supplied video is empty, corrupt or cannot be associated with the delivered implementation
- **THEN** it is not advertised as current approved evidence

### Requirement: Retryable delivery outcomes
The system SHALL distinguish completed, retryable failure, blocked and not-applicable outcomes for required delivery steps. Empty recording and missing upload links SHALL NOT be completed delivery. Recovered executions SHALL revalidate cached artifacts and resume the first incomplete step without repeating valid completed recording or duplicating external effects. Legacy empty checkpoints SHALL be reconciled without removing history.

#### Scenario: Drive outage and restart
- **WHEN** recording and conversion succeed but uploading fails before a restart
- **THEN** recovery reuses the valid MP4 and retries upload without recording again

#### Scenario: Legacy empty completion
- **WHEN** a required delivery has a completed checkpoint containing no artifacts or no link
- **THEN** it remains pending and is safely retried rather than treated as delivered

### Requirement: Delivery requests remain independent of product decisions
Authorized requests to capture, convert, publish or share implementation evidence SHALL be scheduled at a safe point using configured delivery capabilities. Mere delivery requests SHALL NOT require product replanning or imply merge authorization. Requirements SHALL remain pending until completed or explicitly cancelled. Changes to product behavior or demo coverage SHALL retain existing feedback rules.

#### Scenario: Publish an existing demo
- **WHEN** a user asks to upload the demo to Drive and put its link in the PR
- **THEN** delivery is scheduled without changing the pending merge decision or requesting a new product proposal solely for publication

### Requirement: Verifiable reviewer delivery
The system SHALL distinguish uploaded files, inherited folder access, verified PR-link synchronization and actual message delivery. It SHALL always preserve existing folder permissions without creating public or individual grants, recognize effective domain ACLs, preserve human PR edits, pass attachments as actual validated files, and report unmet steps accurately. Local file paths SHALL NOT be presented as delivered attachments or shareable links.

#### Scenario: Already published current evidence
- **WHEN** controller-attested current media matches the existing Drive file and the PR link
- **THEN** finalization reuses that link in its conversation summary without another capture or upload, including after planning-only archival changes

#### Scenario: Inherited domain access
- **WHEN** the destination folder grants domain readership and the uploaded file retains that effective access
- **THEN** codebot verifies inherited access without requiring individual reviewer emails or creating permissions

#### Scenario: Investigation includes attachment markers
- **WHEN** an investigation response identifies valid attachment files
- **THEN** those files are transported through the actual attachment mechanism or their delivery limitation is stated

#### Scenario: Sharing or PR update fails
- **WHEN** upload succeeds but access or PR synchronization fails
- **THEN** the existing upload is preserved, the failed step remains pending, and the response does not claim complete delivery
