## Why

The stitched Playwright evidence video is the one artefact that routinely outgrows
the Gmail attachment cap: `gmail_client.send` silently drops any attachment past
`CODEBOT_MAX_ATTACH_BYTES` and leaves only a filename in the body, so longer demos
never reach the user. And the activity trail on the backlog item (an issue comment
or a doc comment thread) can only list attachment *names* — nobody reading the
ticket can watch the video. The bot's Google token already carries the full `drive`
scope (widened for the activity trail), so Drive is available at no setup cost.

## What Changes

- New `drive_client.upload_evidence(path, name)`: uploads a file to a Drive folder
  (`CODEBOT_DRIVE_FOLDER_ID`, or a `Codebot evidence` folder found/created at the
  root of My Drive), shares it "anyone with the link" as reader, returns the web
  link; best-effort, `None` on any failure. Google imports are lazy so the FSM
  tests keep running without the client libraries.
- `main._offload_evidence_video(state, attachments)`: uploads every `.mp4` in an
  email's attachment list (named `<branch>-<timestamp>.mp4`), removes the uploaded
  ones, records `state["evidence_url"]`. Non-mp4 files (Newman reports, agent
  screenshots) and mp4s whose upload failed stay attached exactly as before.
- The "PR ready for review" and "PR updated" (feedback push) emails carry a
  `Video: <link>` line in the body, so `email()` → `trail()` mirrors it to the
  GitHub issue comment / doc thread with no backend change.
- `CODEBOT_EVIDENCE_UPLOAD` (default on) and `CODEBOT_DRIVE_FOLDER_ID` settings;
  `.env.example`, `scripts/setup.sh` wording and README updated.

## Capabilities

### New Capabilities
- `evidence-delivery`: how the evidence video reaches the user and the ticket —
  Drive upload, sharing, linking, and the attach fallback.

### Modified Capabilities
(none)

## Impact

- New: `src/drive_client.py`, `tests/test_drive_client.py`, `tests/test_evidence_upload.py`.
- `src/main.py`: `_offload_evidence_video`, `finalize_pr` body, `do_push` feedback
  branch, `evidence_url` in `RESET_KEYS`.
- `src/config.py`: `EVIDENCE_UPLOAD`, `DRIVE_FOLDER_ID`, `DRIVE_FOLDER_NAME`.
- Operators whose `data/token.json` predates the full `drive` scope get an attach
  fallback plus a log hint to re-run `scripts/setup_oauth.py`.
