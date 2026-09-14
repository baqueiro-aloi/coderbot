## Purpose

Defines how the evidence video codebot records for a pull request reaches the user
and the backlog item: uploaded to Google Drive and linked, with attachment as the
fallback.

## ADDED Requirements

### Requirement: Evidence video upload
When evidence upload is enabled (`CODEBOT_EVIDENCE_UPLOAD`, default on), codebot
SHALL upload every `.mp4` evidence file bound for a "PR ready for review" or
"PR updated" email to Google Drive, named `<branch>-<timestamp>.mp4`, and SHALL
NOT attach it to the email. Files that are not `.mp4` SHALL be attached as before.

#### Scenario: Stitched video is linked, not attached
- **WHEN** the e2e phase produced a stitched mp4 and the upload succeeds
- **THEN** the PR email body contains a `Video: <link>` line and carries no mp4 attachment

#### Scenario: Newman report stays attached
- **WHEN** the evidence is a Newman html report
- **THEN** no upload is attempted and the report is attached as before

### Requirement: Attach fallback
When upload is disabled or fails for any reason (API error, missing scope, missing
file), codebot SHALL attach the mp4 exactly as it did before this change, subject to
`CODEBOT_MAX_ATTACH_BYTES`, and SHALL log the failure without affecting the task.

#### Scenario: Upload fails
- **WHEN** the Drive upload raises
- **THEN** the email says "Attached: a Playwright video (mp4)" and carries the file

### Requirement: Destination folder
Videos SHALL be stored in the folder given by `CODEBOT_DRIVE_FOLDER_ID` when set;
otherwise in a folder named `Codebot evidence` at the root of the bot account's
My Drive, which codebot SHALL create on first use and reuse afterwards.

#### Scenario: Folder auto-created once
- **WHEN** no folder id is configured and no `Codebot evidence` folder exists
- **THEN** the first upload creates it and later uploads reuse it without searching again

### Requirement: Link sharing
Each uploaded video SHALL be shared with "anyone with the link" as reader. If the
sharing change is rejected, the upload SHALL still count as successful and the link
SHALL still be sent.

#### Scenario: Workspace policy forbids link sharing
- **WHEN** the permission call is rejected
- **THEN** the email still links the video and a warning is logged

### Requirement: Link reaches the activity trail
The video link SHALL be part of the email body so the activity trail note on the
backlog item (issue comment or doc comment thread) carries the same link.

#### Scenario: GitHub issue comment carries the link
- **WHEN** the PR-ready email is sent with an uploaded video
- **THEN** the issue comment posted by the trail contains the same `Video: <link>` line
