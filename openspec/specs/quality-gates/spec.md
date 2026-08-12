# Quality Gates Specification

## Purpose

Defines how codebot gates each task on end-to-end test evidence and automated
code review, how it adapts that gating to target repos that do not provide one
or both of those mechanisms — including seeding a backlog item so it can build
the missing piece itself — and how it supports both Playwright- and
Newman/Postman-based e2e harnesses, so codebot does not require every target
repo to have a frontend, a Playwright harness, or a "Code Review" GitHub Action.

## Requirements

### Requirement: Target repo capability detection
When picking a new task, codebot SHALL determine whether the target repo
provides an e2e test harness (an `e2e/run.sh` script) and whether it provides
an automated code-review workflow (a GitHub Actions workflow file under
`.github/workflows/` whose declared name is "Code Review"). Codebot SHALL
persist both results for the duration of the task so later phases do not need
to re-detect them.

#### Scenario: Target repo has both an e2e harness and a Code Review workflow
- **WHEN** codebot picks a task and finds `e2e/run.sh` and a `.github/workflows/`
  file declaring the workflow name "Code Review" in the target repo
- **THEN** codebot records that both the e2e gate and the code-review gate are
  available for this task

#### Scenario: Target repo has neither
- **WHEN** codebot picks a task and finds no `e2e/run.sh` and no
  `.github/workflows/` file declaring the workflow name "Code Review" in the
  target repo
- **THEN** codebot records that both gates are unavailable for this task and
  does not treat their absence as an error

### Requirement: Conditional E2E gate
Codebot SHALL only run the e2e suite and require it to pass as a condition of
opening a pull request when the target repo was detected to have an e2e
harness for this task. When no harness was detected, codebot SHALL proceed
directly from implementation to opening the pull request without invoking an
e2e run, and SHALL NOT treat the absent harness as a test failure.

#### Scenario: E2E harness present
- **WHEN** the implementation phase completes and an e2e harness was detected
  for this task
- **THEN** codebot runs the e2e suite and only proceeds to open a pull request
  once it passes, resuming the working session to fix failures otherwise

#### Scenario: E2E harness absent
- **WHEN** the implementation phase completes and no e2e harness was detected
  for this task
- **THEN** codebot proceeds directly to opening a pull request without
  attempting to run an e2e suite and without emailing the user about a missing
  harness

### Requirement: Conditional code-review gate
Codebot SHALL only wait for the automated code-review workflow and address its
comments before notifying the user when that workflow was detected for this
task. When no such workflow was detected, codebot SHALL finalize and email the
pull request immediately after opening it, without polling for a review check
that cannot appear.

#### Scenario: Code Review workflow present
- **WHEN** codebot opens a pull request and a Code Review workflow was
  detected for this task
- **THEN** codebot waits for that workflow's check to complete on the pull
  request's head commit, addresses any new inline comments it leaves, and
  repeats until a run leaves no new comments or the round/timeout limit is
  reached, before emailing the user

#### Scenario: Code Review workflow absent
- **WHEN** codebot opens a pull request and no Code Review workflow was
  detected for this task
- **THEN** codebot records evidence and emails the pull request to the user
  immediately, without entering a review-wait phase

### Requirement: E2E harness kind detection
When an e2e harness is present, codebot SHALL determine whether it is a
Playwright harness or a Newman (Postman collection) harness. When no harness
is present, codebot SHALL determine whether the target repo has a frontend, to
decide which kind it would seed a self-healing backlog item for. Both kinds
are invoked identically via `e2e/run.sh` for pass/fail purposes; the kind only
affects task guidance, self-healing item text, and evidence collection.

#### Scenario: Present harness is Playwright
- **WHEN** an e2e harness is detected and the target repo's `e2e/` directory
  contains a Playwright configuration
- **THEN** codebot records the harness kind as Playwright

#### Scenario: Present harness is Newman
- **WHEN** an e2e harness is detected and the target repo's `e2e/` directory
  contains Postman collection files but no Playwright configuration
- **THEN** codebot records the harness kind as Newman

#### Scenario: Target repo has a frontend
- **WHEN** no e2e harness is detected and the target repo has a frontend
  application
- **THEN** codebot treats Playwright as the kind to request when seeding a
  self-healing backlog item

#### Scenario: Target repo has no frontend
- **WHEN** no e2e harness is detected and the target repo has no frontend
  application
- **THEN** codebot treats Newman as the kind to request when seeding a
  self-healing backlog item

### Requirement: Self-healing backlog seeding
When codebot detects that required infrastructure (an e2e harness or a Code
Review workflow) is absent from the target repo, it SHALL add a new pending
item to the backlog describing that gap — naming the appropriate e2e tool
(Playwright or Newman) per the detected target-repo kind for a missing e2e
harness — unless an equivalent item already exists among the backlog's
pending or completed items. Codebot SHALL NOT add a duplicate item for
infrastructure that is already tracked, pending, or done.

#### Scenario: First detection of a missing e2e harness on a frontend repo
- **WHEN** codebot detects no e2e harness during `do_pick`, the target repo
  has a frontend, and no existing backlog item requests an e2e harness
- **THEN** codebot adds a new pending backlog item describing the need for a
  Playwright e2e harness

#### Scenario: First detection of a missing e2e harness on a frontend-less repo
- **WHEN** codebot detects no e2e harness during `do_pick`, the target repo
  has no frontend, and no existing backlog item requests an e2e harness
- **THEN** codebot adds a new pending backlog item describing the need for a
  Newman/Postman e2e harness

#### Scenario: Gap already tracked
- **WHEN** codebot detects a missing piece of infrastructure but a matching
  backlog item already exists, pending or done
- **THEN** codebot does not add another item for the same gap

#### Scenario: Infrastructure later implemented
- **WHEN** a backlog item for missing infrastructure is picked and
  implemented on a later task, and codebot re-detects target-repo
  capabilities on a subsequent task
- **THEN** codebot finds the infrastructure present and the corresponding
  gate (e2e or code-review) behaves as if it had always been present

### Requirement: Kind-aware evidence collection
When recording evidence for the "PR ready for review" email, codebot SHALL
attach evidence appropriate to the detected e2e harness kind: a stitched video
for a Playwright harness, or the generated run report for a Newman harness. If
no evidence artifact is available for the detected kind, codebot SHALL send
the email without an attachment rather than failing.

#### Scenario: Playwright evidence
- **WHEN** codebot finalizes a pull request and the e2e harness kind is
  Playwright
- **THEN** codebot attaches a stitched video demonstrating the feature, as
  today

#### Scenario: Newman evidence
- **WHEN** codebot finalizes a pull request and the e2e harness kind is
  Newman
- **THEN** codebot attaches the Newman run report generated for the relevant
  collection(s) instead of a video

### Requirement: Detection-aware task guidance
When instructing Claude to formalize a proposal or implement it, codebot SHALL
state whether comprehensive e2e tests are mandatory (harness detected) or
whether Claude should instead rely on its own judgment to verify the change
(harness absent), so Claude is never told to add tests to a directory that
does not exist. When e2e tests are mandatory, codebot SHALL tell Claude which
tool to use — Playwright specs under `e2e/tests/` for a Playwright harness, or
Postman collections under `e2e/collections/` run via Newman for a Newman
harness — matching the detected (or, for a newly-seeded harness, the
requested) kind.

#### Scenario: Guidance when harness is absent
- **WHEN** codebot renders the proposal-formalization or implementation prompt
  for a task where no e2e harness was detected
- **THEN** the rendered prompt does not assert that e2e tests are mandatory
  and does not ask Claude to report `E2E_SPEC:` lines

#### Scenario: Guidance for a Playwright harness
- **WHEN** codebot renders the proposal-formalization or implementation prompt
  for a task where a Playwright harness was detected
- **THEN** the rendered prompt asserts that Playwright e2e specs under
  `e2e/tests/` are mandatory

#### Scenario: Guidance for a Newman harness
- **WHEN** codebot renders the proposal-formalization or implementation prompt
  for a task where a Newman harness was detected
- **THEN** the rendered prompt asserts that Postman collections under
  `e2e/collections/`, run via Newman, are mandatory
