## Purpose

Allow coderbot to repair its own execution and repository errors across workflow phases while preserving unrelated work, durable context and verified progress.

## ADDED Requirements

### Requirement: Phase preconditions invoke recovery
When a phase cannot proceed because of a repairable task-owned condition, codebot SHALL diagnose it and enter an appropriate recovery path with a recorded origin and resume target. A phase permission boundary SHALL NOT cause codebot to request administrative authorization for repairing its own task work. Recovery SHALL verify the failed condition before resuming and SHALL invoke replanning when repair requires a material product decision.

#### Scenario: Dirty worktree prevents archival
- **WHEN** archival is blocked by uncommitted test repairs produced for the current task
- **THEN** codebot reviews, verifies and commits those repairs automatically and returns to archival without asking the user to authorize the commit

### Requirement: Recovery preserves work provenance
Codebot SHALL inspect staged and unstaged changes, untracked files, conflicts and incomplete Git operations against recorded task-start and turn provenance. It SHALL preserve unrelated or ambiguous work and isolate the task when needed instead of discarding or incorporating it blindly. Task-owned incomplete repairs SHALL be completed or reverted with recorded reasoning. Required verification repairs SHALL be included in shared task history or a tracked linked follow-up rather than depending solely on a local stash.

#### Scenario: Mixed worktree
- **WHEN** a worktree contains both task-owned repairs and unrelated edits
- **THEN** codebot preserves the unrelated edits and uses an isolated task workspace when ownership cannot be safely separated in place

#### Scenario: Interrupted merge
- **WHEN** a task-owned merge is incomplete after restart
- **THEN** recovery inspects and completes or unwinds that operation before starting another one, preserving both branch intents

### Requirement: Recovery results are explicit and durable
Every recovery turn SHALL yield a verified repair, a delivered pending question, a replanning transition or a recorded technical failure. Codebot SHALL NOT clear a blocker or lose a question just because a recovery turn returned. Recovery context and progress SHALL survive restarts and held tasks; identical unsuccessful preconditions SHALL trigger diagnosis rather than repeated no-op attempts.

#### Scenario: Agent asks during recovery
- **WHEN** a recovery agent returns a question instead of completing its repair
- **THEN** codebot delivers the question, waits for the answer and retains the original blocker and resume target

### Requirement: Technical retries do not consume functional rounds
Codebot SHALL distinguish transient connectivity failures, infrastructure failures, product failures and unknown outcomes. Transient agent connectivity failures including `fetch failed` SHALL use bounded increasing-delay retries preserving checkpoints, without consuming completed review rounds. Prolonged unavailability SHALL produce one concise incident notice with diagnostics and a concrete recovery status. Only completed functional work SHALL consume a functional review round.

#### Scenario: Connection fails before review work
- **WHEN** OpenCode exits with `fetch failed` before producing a review result
- **THEN** the technical retry count increases while the completed review-round count remains unchanged

#### Scenario: No effective progress
- **WHEN** successive recovery attempts encounter the same condition without changing it
- **THEN** codebot stops blindly retrying and records a revised diagnosis or concrete unresolved decision
