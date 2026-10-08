# Evidence delivery and recovery

Evidence is not delivered merely because a WEBM exists. Codebot validates the run,
binds artifacts to the implementation snapshot, probes playable MP4 media, verifies
Drive permissions, reads back the PR video section and sends the actual link/files.
No evidence belongs in Git.

## Configuration

- `CODEBOT_EVIDENCE_UPLOAD=on` enables upload.
- `CODEBOT_DRIVE_FOLDER_ID` selects an authorized destination; empty uses the existing
  `Codebot evidence` folder convention.
- `CODEBOT_DRIVE_SHARE_MODE=inherited` (default) changes no permissions and requires
  `CODEBOT_DRIVE_REVIEWERS` email identities whose access can be verified.
- `CODEBOT_DRIVE_SHARE_MODE=reviewers` grants reader access only to those identities.
- `CODEBOT_DRIVE_SHARE_MODE=anyone` explicitly authorizes anyone-with-link access.
  Do not select it without permission to make this evidence public.

The Google token needs Drive write scope. Do not paste tokens or secrets into Slack.
Upload failure is retryable; unconfigured reviewer access is blocked, not successful.
An uploaded file is reused by SHA-256 if permissions need repairing.

## Separate PICA harness correction

The target's `e2e/validate-results.cjs` currently parses `--grep` but counts the complete
selected-file inventory. In a separately authorized PICA change, filter inventory
titles with the same Playwright selection semantics before validating count and
membership. Preserve the complete unfiltered inventory gate.

Acceptance: four passing `@evidence` demos with four current-run videos succeed;
grep/invert and inline-option forms select the correct inventory; zero matches,
missing cases, skips, failures, retries, report errors, missing/duplicate videos and
an incomplete unfiltered suite fail. Codebot does not waive a rejected harness exit.
Its diagnostics distinguish capture from post-capture validation and retain clips.

## Deployment and PR #114 recovery

1. Review and test the codebot change; separately correct/test the PICA validator.
2. Obtain explicit deployment authorization and configure authorized Drive access.
3. Stop the controller safely. Check separately spawned E2E containers: compose down
   of codebot does not necessarily terminate those projects. Do not delete unrelated
   projects or worktree changes.
4. Deploy, retaining SQLite, manifests, source media and OAuth data. Invalid legacy
   empty checkpoints are revalidated lazily without deleting audit history.
5. Request delivery in the existing task thread, without authorizing merge. Confirm
   the current PR head and reconcile working changes. Existing media without trusted
   matching provenance must be regenerated, not assumed current.
6. Confirm playable MP4, remote file and reviewer access, PR section read-back and
   actual conversation link. Keep review/merge gates unchanged.

Rollback: stop the controller and restore the prior code only; retain data and media.
Prior code may not understand new delivery metadata and does not enforce verified
sharing. Keep publication disabled until a compatible version is deployed. Never
restore an old state.json over new work or delete delivery history just to force retry.
