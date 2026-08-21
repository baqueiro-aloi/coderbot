## Why

Onboarding a new target project today means hand-editing `.env` against the
README's "One-time setup" checklist (`CODEBOT_REPO_PATH`, `CODEBOT_DOC_ID`,
`CODEBOT_USER_EMAIL`, `GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`,
`GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL`, plus the Google OAuth
`data/credentials.json` step and optional vars), with no in-the-moment
explanation of what each value is or where to get it. That's error-prone (a
typo'd path or a token pasted into the wrong variable fails silently or late)
and raises the bar for pointing codebot at a new project. A guided,
interactive `setup.sh` turns that checklist into a script that asks for each
value one at a time, explains it concisely, and writes a valid `.env`.

## What Changes

- Add a `setup.sh` at the repo root: an interactive bash script that walks
  through every `.env` variable from `.env.example`, printing a one- or
  two-line explanation of what it is and where to get it before prompting.
- Pre-fill sensible defaults where discoverable and let the user accept or
  override them: `GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL` from `git config
  --global user.name`/`user.email`; `GH_TOKEN` from `gh auth token` when the
  `gh` CLI is authenticated; `CODEBOT_PROJECT_NAME` from the basename of the
  entered `CODEBOT_REPO_PATH`.
- Validate what can be cheaply validated as each value is entered:
  `CODEBOT_REPO_PATH` is an absolute path to an existing git repository;
  `CODEBOT_DOC_ID` accepts either a raw id or a full Google Docs URL (extract
  the id); `CODEBOT_USER_EMAIL` has a plausible `user@host` shape. Re-prompt
  on failure rather than writing a value known to be wrong.
- Check for `data/credentials.json` (the Google OAuth client JSON, which
  requires a manual Cloud Console step this script cannot automate) and, if
  missing, print the exact steps to obtain it and pause; if present, offer to
  run `python3 setup_oauth.py` immediately afterward to complete the consent
  flow that produces `data/token.json`.
- Write the collected values to `.env` at the repo root, backing up any
  existing `.env` first (e.g. to `.env.bak.<timestamp-suffix>`) and confirming
  before overwrite. Restrict the written file's permissions (e.g. `chmod
  600`) since it holds secrets.
- Never echo secret values back to the terminal after entry, and never log
  them; the script's own prompts are the only place they're described.
- Update the README's "One-time setup" section to lead with `./setup.sh` as
  the recommended path, keeping the manual `.env.example`-based steps as a
  documented fallback.

## Capabilities

### New Capabilities
- `interactive-setup`: A guided, validating command-line setup flow that
  collects codebot's required and optional configuration for a target
  project and writes it to `.env`, replacing manual editing against
  `.env.example`.

### Modified Capabilities
(none)

## Impact

- New `setup.sh` at the repo root.
- `README.md`: "One-time setup" section reordered/updated to lead with
  `./setup.sh`.
- No changes to `main.py`, `config.py`, `claude_runner.py`, `evidence.py`,
  `gdoc_client.py`, `gmail_client.py`, `google_auth.py`, `entrypoint.sh`,
  `setup_oauth.py`, or Docker/compose files — `setup.sh` only produces the
  `.env` those already consume, and may invoke `setup_oauth.py` and `gh auth
  token` as external commands.
