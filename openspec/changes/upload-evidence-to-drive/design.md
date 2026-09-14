## Context

`evidence.record_evidence` returns the stitched `data/evidence.mp4` (overwritten
every round) and two composition sites email it: `finalize_pr` ("PR ready for
review") and the feedback branch of `do_push` ("PR updated" — the attachment paths
travel through `state["push_context"]` between ticks). `main.email()` sends the
message and then mirrors its body to the backlog item via `trail()` →
`task_source.note_activity`. `gdoc_client` already builds a Drive v3 service for
doc comments; `config.SCOPES` includes the full `drive` scope.

## Goals / Non-Goals

**Goals**
- The video is always deliverable regardless of size, and watchable from the ticket.
- Zero behaviour change when upload is off or fails: the mp4 is attached as today.
- No new dependencies, no startup network calls, no re-consent for current tokens.

**Non-Goals**
- Uploading Newman reports or agent screenshots (small, and fine as attachments).
- Deleting or expiring old videos in Drive.
- Restricting sharing per viewer; "anyone with the link" is the chosen policy.

## Decisions

- **Suffix predicate.** Any `.mp4` attachment is a stitched evidence video (agent
  `.webm` clips are stitched by `_collect_attachments` before they reach an email),
  so filtering on suffix is exact and needs no extra bookkeeping.
- **Link in the body, at the two composition sites, not inside `email()`.** The
  callers phrase the "Attached:" vs "Video:" sentence precisely, and existing tests
  that assert on `email.call_args` extend naturally. Putting the body line in the
  email means the trail mirrors it for free, on every backend.
- **Offload in `do_push`, not where attachments are collected.** One site instead
  of two, and nothing new to persist in `push_context`. A retried push after a
  failed `git push` re-uploads; the timestamped name makes that a harmless duplicate.
- **Naming `<branch>-<timestamp>.mp4`.** The branch carries the instance name, so
  concurrent instances and re-finalizes cannot collide even though the local file
  name is fixed.
- **Sharing failure keeps the link.** If a Workspace policy rejects
  `permissions.create(anyone)`, the file is still uploaded and the owner can open
  it; falling back to a 20 MB attachment would be worse. Logged loudly.
- **Lazy Google imports in `drive_client`.** `main.py` imports it at module top and
  the FSM tests run without `googleapiclient` installed.
- **Folder cache cleared on error.** A trashed folder or a bad
  `CODEBOT_DRIVE_FOLDER_ID` is re-resolved on the next upload instead of failing
  every time.

## Risks / Trade-offs

- Drive quota or API outage → attach fallback, which may still hit the Gmail cap
  for long videos (the pre-existing failure mode, now the exception not the rule).
- "Anyone with the link" is unlisted, not private: the URL is as sensitive as the
  PR link it sits next to.
