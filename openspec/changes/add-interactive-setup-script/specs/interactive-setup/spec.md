## Purpose

Defines the guided command-line setup flow that collects codebot's
configuration for a target project — required and optional environment
variables plus the Google OAuth credential file — and writes a valid `.env`,
so pointing codebot at a new project does not require manually transcribing
values against `.env.example` or manually navigating the Google Cloud
Console unguided.

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

### Requirement: Guided Google OAuth credential setup
The setup script SHALL actively guide the user through obtaining the Google
OAuth client credential file, not just describe the steps: for each action
that must happen in the Google Cloud Console (selecting/creating a project,
enabling the required APIs, creating the OAuth client), it explains what is
about to happen, opens the relevant console page in the user's browser when
a browser-opening command is available, and waits for the user to confirm
before continuing. It SHALL NOT attempt to create the credential file
itself, since obtaining it requires actions only the user can take in the
console. Once the file is in place, the setup script SHALL run the consent
flow that produces the OAuth token file automatically, without asking.

#### Scenario: Guiding project selection
- **WHEN** the Google OAuth credential file is not present and the walkthrough
  begins
- **THEN** the setup script explains that a project must be selected or
  created, opens the Cloud Console's project page, and waits for the user to
  press Enter before continuing

#### Scenario: Guiding API enablement
- **WHEN** the user has confirmed a project is selected
- **THEN** the setup script explains which APIs are required (Gmail, Docs,
  Drive), opens each API's enable page, and waits for the user to confirm all
  three are enabled before continuing

#### Scenario: Guiding OAuth client creation
- **WHEN** the required APIs have been confirmed enabled
- **THEN** the setup script explains how to create a Desktop-app OAuth client
  and download its JSON, opens the Cloud Console's credentials page, and
  repeatedly checks for the downloaded file at the expected path until it is
  found or the user chooses to skip

#### Scenario: Browser cannot be opened automatically
- **WHEN** the setup script has no way to open a browser automatically (no
  `open`/`xdg-open`-equivalent command available)
- **THEN** it prints the console URL for the user to open manually instead of
  failing

#### Scenario: Credential file already present
- **WHEN** the setup script runs and the expected Google OAuth credential
  file is already present
- **THEN** it skips the project/API/client-creation walkthrough entirely

#### Scenario: Consent flow runs automatically once the file is in place
- **WHEN** the Google OAuth credential file is present (whether already
  present at the start, or just placed there during the walkthrough)
- **THEN** the setup script runs the consent flow that produces the OAuth
  token file automatically, without asking for confirmation first

#### Scenario: OAuth already fully configured
- **WHEN** the setup script runs and the OAuth token file already exists
- **THEN** it skips the entire Google OAuth section with a note that it is
  already configured, instead of repeating the walkthrough

### Requirement: Bulk reuse of an existing .env
When an existing `.env` is found, the setup script SHALL offer to keep it
unchanged and skip the variable-collection prompts entirely, in addition to
offering each existing value as a per-variable default.

#### Scenario: User keeps the existing .env as-is
- **WHEN** an existing `.env` is found and the user confirms they want to
  keep it unchanged
- **THEN** the setup script skips every required and optional variable
  prompt and does not rewrite `.env`

#### Scenario: User opts to review values
- **WHEN** an existing `.env` is found and the user declines to keep it
  unchanged
- **THEN** the setup script proceeds through each prompt as usual, offering
  the existing value as the default for each

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
