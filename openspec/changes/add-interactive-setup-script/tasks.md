## 1. Script scaffold

- [x] 1.1 Create `setup.sh` at the repo root, executable, `set -euo pipefail`,
      running from the repo root regardless of caller's cwd.
- [x] 1.2 Add a small prompt helper (label, explanation, default, secret?) used
      by every variable below, so each variable is a one-line call.
- [x] 1.3 If `.env` already exists, parse its current values to seed as
      defaults for the corresponding prompts below (see design.md).

## 2. Required variables

- [x] 2.1 Prompt for `CODEBOT_REPO_PATH` with an explanation (absolute path to
      the target git checkout); validate it is absolute and an existing git
      repo, re-prompting on failure.
- [x] 2.2 Prompt for `CODEBOT_DOC_ID` with an explanation (the backlog Google
      Doc's id, found in its URL); accept a full URL and extract the id.
- [x] 2.3 Prompt for `CODEBOT_USER_EMAIL` with an explanation; validate a
      plausible `user@host` shape, re-prompting on failure.
- [x] 2.4 Prompt for `GH_TOKEN` with an explanation (PAT with repo scope);
      default to `gh auth token`'s output when `gh` is installed and
      authenticated; use `read -s` (no echo).
- [x] 2.5 Prompt for `CLAUDE_CODE_OAUTH_TOKEN` with an explanation (output of
      `claude setup-token`, run by the user themselves); use `read -s`.
- [x] 2.6 Prompt for `GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL` with an explanation;
      default from `git config --global user.name`/`user.email` when set.

## 3. Optional variables

- [x] 3.1 Prompt for `CODEBOT_PROJECT_NAME` with an explanation (defaults to
      the repo dir name if left blank); default to the basename of the entered
      `CODEBOT_REPO_PATH`, accepting an empty answer.
- [x] 3.2 Prompt for `CLAUDE_MODEL` with an explanation and its default
      (`claude-opus-4-8`), accepting an empty answer.
- [x] 3.3 Prompt for `CODEBOT_LOG_LEVEL` with an explanation (`DEBUG` or
      `INFO`) and its default (`DEBUG`), accepting an empty answer.

## 4. Google OAuth credential handoff

- [x] 4.1 Check for `data/credentials.json`; if missing, print the Cloud
      Console steps to obtain it (project, enable Gmail/Docs/Drive APIs,
      create a Desktop-app OAuth client, download JSON to that path) and
      continue without failing setup.
- [x] 4.2 If `data/credentials.json` is present, offer to run `python3
      setup_oauth.py` immediately (after confirming `pip install -r
      requirements.txt` has been run, or running it if not).

## 5. Writing .env

- [x] 5.1 If `.env` already exists, back it up to a non-clobbering path
      (`.env.bak.<n>`) and confirm the overwrite with the user before writing.
- [x] 5.2 Write all collected required and optional values to `.env` in the
      same shape as `.env.example`.
- [x] 5.3 `chmod 600 .env` after writing.
- [x] 5.4 Print a summary of what was written (variable names only, never
      secret values) and the next command to run (`docker compose up -d
      --build`).

## 6. Documentation

- [x] 6.1 Update the README's "One-time setup" section to lead with
      `./setup.sh` as the recommended path, keeping the manual
      `.env.example`-based steps documented as a fallback.

## 7. Verification

- [x] 7.1 Ran `setup.sh` (via bash 3.2, macOS's default `/bin/bash` — no
      `declare -A`/bash-4 support, which caught a real portability bug) against
      an isolated scratch git repo end-to-end: relative-path/non-git-dir repo
      path rejected then a valid one accepted; a full Google Docs URL had its
      id correctly extracted; a malformed email was rejected then a valid one
      accepted; blank optional/default-bearing prompts fell back to git
      config / `claude-opus-4-8` / `DEBUG` as expected; the missing
      `data/credentials.json` case printed the manual steps without erroring;
      the resulting `.env` had exactly the entered/defaulted values and mode
      `600`.
- [x] 7.2 Re-ran against the same sandbox with that `.env` present: every
      prompt (including the two secrets) offered the existing value as the
      default when left blank, a `data/credentials.json`-present run offered
      (and, on decline, skipped) the consent flow, and confirming the
      overwrite backed up the old file to `.env.bak.1` before writing the new
      one with identical values. Declining the overwrite left the original
      `.env` untouched and exited non-zero.
