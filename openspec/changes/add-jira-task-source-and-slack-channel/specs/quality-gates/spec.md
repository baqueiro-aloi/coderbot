## MODIFIED Requirements

### Requirement: Conditional code-review gate
Codebot SHALL only wait for the automated code-review workflow and address its comments before notifying the user through the selected communication channel when that workflow was detected for this task. When no such workflow was detected, codebot SHALL finalize and send the pull request through that channel immediately after opening it, without polling for a review check that cannot appear.

#### Scenario: Code Review workflow present
- **WHEN** codebot opens a pull request and a Code Review workflow was detected for this task
- **THEN** codebot waits for that workflow's check to complete on the pull request's head commit, addresses any new inline comments it leaves, and repeats until a run leaves no new comments or the round/timeout limit is reached, before notifying the user via the selected channel

#### Scenario: Code Review workflow absent
- **WHEN** codebot opens a pull request and no Code Review workflow was detected for this task
- **THEN** codebot records evidence and sends the pull request through the selected channel immediately, without entering a review-wait phase

### Requirement: Kind-aware evidence collection
When recording evidence for the "PR ready for review" handoff, codebot SHALL deliver evidence appropriate to the detected e2e harness kind through the selected communication channel: a stitched video for a Playwright harness, or the generated run report for a Newman harness. Large video evidence SHALL continue to be uploaded to Google Drive and linked from the handoff when evidence upload is enabled. If no evidence artifact is available for the detected kind, codebot SHALL send the handoff without evidence rather than failing.

#### Scenario: Playwright evidence
- **WHEN** codebot finalizes a pull request and the e2e harness kind is Playwright
- **THEN** codebot provides the stitched video in the selected channel, using its Google Drive link when uploaded, as today

#### Scenario: Newman evidence
- **WHEN** codebot finalizes a pull request and the e2e harness kind is Newman
- **THEN** codebot provides the generated Newman run report for the relevant collection(s) in the selected channel instead of a video
