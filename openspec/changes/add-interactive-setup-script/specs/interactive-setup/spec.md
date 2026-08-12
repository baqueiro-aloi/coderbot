## Purpose

Defines the guided command-line setup flow that collects codebot's
configuration for a target project — required and optional environment
variables plus the Google OAuth credential file — and writes a valid `.env`,
so pointing codebot at a new project does not require manually transcribing
values against `.env.example`.

## ADDED Requirements

### Requirement: Guided prompting with explanation
The setup script SHALL prompt for every variable `.env` requires (both
required and optional), one at a time, printing a concise explanation of what
the value is and where to obtain it immediately before each prompt.

#### Scenario: Prompting a required variable
- **WHEN** the setup script reaches a required variable (e.g.
  `CODEBOT_DOC_ID`)
- **THEN** it prints a one- or two-line explanation of what the value is and
  where to find it, then prompts for input

#### Scenario: Prompting an optional variable
- **WHEN** the setup script reaches an optional variable (e.g.
  `CODEBOT_PROJECT_NAME`)
- **THEN** it explains the variable, states its default behavior if left
  blank, and accepts an empty answer without error

### Requirement: Discoverable defaults
Where a value can be discovered from the local environment, the setup script
SHALL pre-fill it as a default the user can accept or override, rather than
requiring it to be retyped.

#### Scenario: Git author identity available
- **WHEN** `git config --global user.name` and `user.email` are set
- **THEN** the setup script offers them as the default for
  `GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL`

#### Scenario: Authenticated gh CLI available
- **WHEN** the `gh` CLI is installed and authenticated
- **THEN** the setup script offers `gh auth token`'s output as the default
  for `GH_TOKEN`

#### Scenario: No discoverable default
- **WHEN** a value has no discoverable local default (e.g.
  `CODEBOT_USER_EMAIL`)
- **THEN** the setup script prompts with no pre-filled default and requires
  explicit input

### Requirement: Input validation with re-prompt
The setup script SHALL validate each value it can cheaply check as it is
entered, and re-prompt on an invalid value rather than writing it to `.env`.

#### Scenario: Invalid repo path
- **WHEN** the entered `CODEBOT_REPO_PATH` is not an absolute path to an
  existing git repository
- **THEN** the setup script reports the problem and re-prompts for
  `CODEBOT_REPO_PATH` without proceeding

#### Scenario: Doc URL instead of raw id
- **WHEN** the entered `CODEBOT_DOC_ID` value is a full Google Docs URL
  rather than a bare id
- **THEN** the setup script extracts the document id from the URL and
  proceeds with the extracted id

#### Scenario: Malformed email
- **WHEN** the entered `CODEBOT_USER_EMAIL` does not have a plausible
  `user@host` shape
- **THEN** the setup script reports the problem and re-prompts for
  `CODEBOT_USER_EMAIL` without proceeding

### Requirement: Google OAuth credential handoff
The setup script SHALL check for the Google OAuth client credential file the
Gmail/Docs/Drive integration requires, and SHALL NOT attempt to create it
itself, since obtaining it requires a manual Google Cloud Console step.

#### Scenario: Credential file missing
- **WHEN** the setup script runs and the expected Google OAuth credential
  file is not present
- **THEN** it prints the exact manual steps to obtain the file and where to
  place it, and does not treat this as a fatal error for the rest of setup

#### Scenario: Credential file present
- **WHEN** the setup script runs and the expected Google OAuth credential
  file is present
- **THEN** it offers to run the consent flow that produces the OAuth token
  file immediately, before finishing

### Requirement: Safe .env output
The setup script SHALL write the collected configuration to `.env` at the
repo root without discarding any pre-existing `.env` or exposing secret
values unnecessarily.

#### Scenario: Existing .env present
- **WHEN** an `.env` file already exists at the repo root
- **THEN** the setup script backs it up before writing the new one and asks
  for confirmation before overwriting

#### Scenario: Secrets not echoed
- **WHEN** the setup script collects a secret value (e.g. `GH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN`)
- **THEN** it does not print that value back to the terminal or write it
  anywhere other than the resulting `.env`

#### Scenario: Restricted file permissions
- **WHEN** the setup script finishes writing `.env`
- **THEN** the file's permissions are restricted to the owner (e.g. `600`)
