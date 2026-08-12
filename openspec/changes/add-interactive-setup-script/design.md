## Context

The variables to collect and their semantics are already fully specified by
`.env.example` and the README's "One-time setup" section (`config.py` reads
them at runtime). This change only adds a guided way to produce `.env`; it
does not add, remove, or rename any variable. `setup_oauth.py` and `gh` are
existing external commands this script shells out to, not code it duplicates.

## Goals / Non-Goals

**Goals:**
- Make first-time (and repeat, e.g. onboarding a second target project)
  configuration a single guided command instead of a manual `.env.example`
  transcription.
- Keep the script dependency-free beyond what's already assumed (`bash`,
  `git`; `gh` and `python3`/`setup_oauth.py` are optional/best-effort, not
  hard requirements of `setup.sh` itself).
- Never write a `.env` known to contain an invalid value for something
  cheaply checkable.

**Non-Goals:**
- Automating the Google Cloud Console OAuth-client-creation step — that's an
  external manual action; the script only detects and hands off to it.
- Running inside the codebot Docker container — `setup.sh` runs on the host,
  before `docker compose up`, same as `setup_oauth.py` today.
- Editing or migrating an existing `.env`'s values in place; a re-run always
  starts from the prompts and offers the existing file's own values back as
  defaults where present (see Decisions), rather than diffing/patching it.

## Decisions

- **Single POSIX/bash script (`setup.sh`), not a Python script.** The repo
  already mixes a bash `entrypoint.sh` with Python application code;
  `setup.sh` runs host-side before any Python environment is guaranteed set
  up (it's what produces the `.env` that later steps consume), so bash with
  no dependency beyond coreutils/`git`/optionally `gh` is the smaller ask.
- **Variable list and prompts are hand-declared in the script, in the same
  order as `.env.example`**, rather than parsed from `.env.example` at
  runtime — the explanatory text per variable (what it is, where to get it)
  has no home in `.env.example`'s single-line comments today, and hand-owned
  prompt strings keep that text reviewable in the script itself rather than
  split across two files.
- **Re-running the script offers current `.env` values as defaults.** If
  `.env` already exists, its parsed values (not just the local-environment
  defaults in the proposal) become the pre-filled default for each prompt
  before backup-and-overwrite, so re-running to change one setting doesn't
  require re-entering everything else, including secrets already on disk.
- **Secret prompts use `read -s`** (no terminal echo) for `GH_TOKEN` and
  `CLAUDE_CODE_OAUTH_TOKEN`; non-secret prompts echo normally so the user can
  see/edit what they typed.
- **`gh auth token` and `git config` defaults are best-effort, not hard
  dependencies.** If `gh` is missing or unauthenticated, or git config is
  unset, the script falls back to an empty default and a plain prompt — it
  never fails setup because an optional discovery command isn't available.
- **`CLAUDE_CODE_OAUTH_TOKEN` is entered by hand, not auto-run.** Unlike `gh
  auth token` (non-interactive, safe to shell out to for a default),
  `claude setup-token` is itself an interactive flow (opens a browser). The
  script explains the command and prompts for its output rather than
  invoking it, to avoid nesting two interactive flows.
- **Backup naming: `.env.bak.<n>`, incrementing to avoid clobbering a
  previous backup**, checked before write; the script confirms the overwrite
  with the user before touching the existing file at all.
- **`data/credentials.json` presence is the trigger for offering
  `setup_oauth.py`.** Reuses `config.CREDENTIALS_PATH` conceptually (the
  script hard-codes the same `data/credentials.json` relative path since it
  runs before `.env` — and therefore any env-driven path override — exists).

## Risks / Trade-offs

- [Hand-declared prompts drift from `.env.example` if a variable is added
  there later without updating `setup.sh`] → No automatic detection of this
  drift; mitigated only by keeping both in the same PR when a variable
  changes (a documentation/review discipline, not a runtime check).
- [`read -s` secret entry means a pasted value can't be visually confirmed
  before submission] → Acceptable: this matches how secrets are normally
  entered (e.g. `ssh-add`, `sudo -S`); a wrong paste is caught the same way a
  wrong manually-edited `.env` value would be — by codebot failing at runtime
  with an auth error, at which point re-running `setup.sh` fixes it.
- [Running `setup.sh` twice against the same `.env` accumulates backup
  files over time] → Low cost (small text files); not addressed by this
  change (no automatic pruning).
