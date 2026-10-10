## Purpose

Gives each Coderbot installation a memorable, stable identity that connects its backlog claims, branches and Slack conversations while preserving existing installations' identities.

## ADDED Requirements

### Requirement: Automatic readable instance identity
For a new installation without an existing persisted identity or explicit override, Coderbot SHALL generate and persist a lowercase, hyphen-separated name with the shape `codebot-<adjective>-<animal>` and reuse it across restarts. Independently of the readable name, each installation SHALL generate and persist a distinct, opaque ownership fingerprint. The readable name SHALL appear in branch names, logs and Slack root messages; backlog claim and hold markers SHALL carry both name and fingerprint. A marker bearing the same name but a different fingerprint SHALL belong to another instance and SHALL NOT be removed or adopted as this installation's claim.

#### Scenario: First startup
- **WHEN** a new installation starts without a configured or saved instance name
- **THEN** it generates and saves a readable name such as `codebot-warty-warthog`

#### Scenario: Restart
- **WHEN** that installation restarts after the name was saved
- **THEN** it continues using exactly the same name and fingerprint and recognizes its own claims

#### Scenario: Matching names on a shared backlog
- **WHEN** two independently installed bots happen to have the same readable name but different fingerprints
- **THEN** each treats the other's claim or hold marker as foreign and neither removes or resumes the other's task

#### Scenario: Existing instance upgrades
- **WHEN** an existing installation already has a valid persisted name such as `codebot-x7k2`, or an explicit instance override
- **THEN** Coderbot retains that readable identity, generates its fingerprint if missing, and migrates only claims corroborated by its locally persisted active or held task state

#### Scenario: Legacy marker without corroborating local state
- **WHEN** an untagged legacy claim has the same readable name but no matching persisted active or held task on this installation
- **THEN** Coderbot does not assume it owns the task and reports that manual reconciliation is needed

### Requirement: Per-instance Slack app identity
Each Slack-enabled Coderbot installation SHALL use its own Slack app credentials and bot identity; the instance name SHALL be visible in its Slack task-root message even if the Slack app's display name differs. An instance SHALL NOT take commands from another instance's task thread in the shared channel.

#### Scenario: Two bots share a channel
- **WHEN** two installations with separate Slack apps work tasks in the same public channel
- **THEN** each handles replies only in the threads it owns
