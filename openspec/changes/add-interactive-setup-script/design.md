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
- Fully automating the Google Cloud Console OAuth-client-creation step —
  creating the project, enabling APIs, and creating the OAuth client are
  actions only the user can take (Google requires interactive
  sign-in/consent); the script opens the right page for each step and walks
  the user through it, but does not click through the console itself.
- Running inside the codebot Docker container — `setup.sh` runs on the host,
  before `docker compose up`, same as `setup_oauth.py` today.
- Editing or migrating an existing `.env`'s values in place; a review pass
  always starts from the prompts and offers the existing file's own values
  back as defaults where present (see Decisions), rather than diffing/
  patching it. Bulk "keep everything" (see Decisions) is a full skip, not a
  partial edit.

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
- **Browser opening: `open` (macOS) or `xdg-open` (Linux), best-effort, with
  the URL always printed too.** The script always prints the console URL
  before/while attempting to open it, so a headless session (no `open`/
  `xdg-open`, or no display) degrades to "copy this URL" rather than
  silently doing nothing — same best-effort principle as the `gh`/git-config
  defaults, applied to a command that can outright fail with no usable
  stderr signal in a headless SSH session.
- **The guided OAuth walkthrough is staged with explicit pauses (`read -p
  "Press Enter..."`), not a single wall of instructions.** Each stage
  (project, APIs, OAuth client, file placement) explains itself, opens its
  page, and waits, so the user is never looking at three URLs' worth of
  instructions at once wondering which browser tab corresponds to which
  step. Deep links to each API's own enable page
  (`console.cloud.google.com/apis/library/<api>.googleapis.com`) are used
  instead of the generic API library search page, since Cloud Console
  deep links honor whichever project the user just selected in their
  browser session — the script never needs to know the project id itself.
- **Waiting for the downloaded credential file re-checks in a loop, with an
  explicit `skip` escape hatch.** Mirrors the existing repo-path/doc-id/email
  validation loops (re-prompt on a not-yet-true condition), but here the
  "invalid" state is just "not there yet" rather than a malformed value, and
  the user can type `skip` to defer entirely rather than being forced to
  either produce the file or Ctrl-C.
- **Once the credential file is confirmed present, `setup_oauth.py` always
  runs immediately** — no separate yes/no prompt for that step, since the
  user already explicitly confirmed placing the file two prompts earlier;
  asking again would be redundant. Its failure is caught and reported as a
  note rather than aborting the rest of the script (see Risks).
- **`data/token.json` presence short-circuits the entire OAuth section.**
  Reuses `config.TOKEN_PATH` conceptually (same relative-path reasoning as
  `CREDENTIALS_PATH`). Re-running `setup.sh` after OAuth is already done
  should not re-walk the user through Cloud Console for no reason.
- **Bulk "keep existing .env" is a single yes/no gate at the very top of the
  variable-collection flow, before any prompt.** Answered once; declining
  falls through to the existing per-variable-default behavior unchanged.
  Accepting skips straight to the (independent) OAuth section — that
  section's own already-configured checks (`credentials.json`/`token.json`)
  govern whether it does anything, not the `.env`-keep decision.

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
- [`setup_oauth.py` fails or is cancelled mid-flow (e.g. the user closes the
  consent browser tab)] → The script reports it and tells the user how to
  retry (`python3 setup_oauth.py`) rather than aborting setup entirely — the
  `.env` values (or the decision to keep them) are unaffected either way.
- [The Cloud Console UI changes its flow/URLs over time] → The deep links
  used (project selector, per-API library pages, credentials page) are
  Google's own stable, documented console URLs, not scraped or versioned;
  if Google changes them, the walkthrough degrades to "opens the wrong page"
  rather than failing outright, and the printed URL still tells the user
  where it meant to go.
