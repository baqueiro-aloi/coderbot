# Integration evidence and explicit validation exceptions

This work is being introduced incrementally under
`openspec/changes/harden-integration-evidence-and-safety/`. Its checklist is the
completion authority. Existing modules and prompts do not imply every planned
gate or secret-provider integration is already implemented.

## Investigation contract

Exploration emits one standalone `INTEGRATION_INVENTORY:` JSON object, version
`1`, with an `integrations` array. An explicitly empty array means exploration
found no affected integration; missing output does not establish that fact.

Each entry identifies `id`, `kind` (`internal` or `external`),
`versions` (`declared`, `installed`, `deployment`), `sources`
(`url`, `consulted_at`, `version`, `evidence`), a `contract`
(`method`, `route`, `auth`, `isolation`, `request`, `response`, `errors`,
`capabilities`), `assumptions` and exact validation `checks` ids. Internal
entries also identify existing repository `implementation` and `consumers`
paths. Assumptions identify `claim`, `status` (`confirmed`, `pending`,
`contradicted`), `material`, `impact` and `next_action`.

The controller validates structure, source-version correspondence and internal
path containment. A source URL and quoted evidence are investigation claims,
not independent proof of a live request or a verified documentation fetch.
Material pending assumptions prevent a dependent planning handoff. Invalid or
missing inventories return to bounded exploration instead of fabricating facts.
Legacy tasks without this contract are not silently assigned an empty inventory.

## Early credentials and budget request

Exploration can report one `CREDENTIAL_REQUEST:` version `1` object together
with `CHECK_PLAN:` version `2`. Required request fields are:

- `service`, `environment`, `env_keys`, `permissions`, exact `check_ids`;
- `effects`, boolean `paid`, numeric nonnegative `max_cost`, `currency`.

Credential variable names must match those declared by the selected checks.
Remote checks identify `kind` (`upstream` or `postdeployment`),
`external_dependencies`, `env_keys` and positive `max_age_seconds`.
Planning records these checks without executing them.

The user is offered secure provisioning, continuing without credentials by
omitting the specified dependent checks, or keeping work paused. Possessing a
key does not authorize the proposed budget. Paid operations remain pending
unless a scoped authorization is recorded. A positive proposed cost is not
itself approval or an enforced provider billing cap.

**Secret intake is not complete yet.** Do not send a plaintext credential or
assume a PrivateBin link is currently resolved safely. Use already provisioned
runtime credentials or explicitly choose continuation without credentials until
the private receiver, expiration and recovery tasks are completed.

## Exceptions

The controller evaluates the entire reply, including negations and conditions.
It records exact existing check ids, operation-scope identities, original human
instruction, reason, channel message id and verified author. No author receipt
means no exception is fabricated. Slack retains author ids across inbox recovery;
email checks the configured sender list.

Exceptions survive state serialization and apply to unchanged check contracts.
Changing the check operation or capability scope requires review; a source-code
snapshot change alone does not expand or revoke consent. Normal focused execution
and final checks must both honor applicable omissions. Reports use `not_run`
with an accepted exception, never a synthetic `pass`. Other checks and security,
retention, proposal approval, merge and deployment controls remain required.

The rollout/migration of older waivers and all lateral conversation paths remains
part of the active checklist. Do not infer completion from the presence of helper
functions or a single passing unit suite.

## Verification boundaries

Known test reporters retain executed/skipped counts. Zero tests produce
`not_run`; skipped tests remain visible. Local SDK/mocks do not demonstrate
upstream inference, tools, streaming or authorization. Newman successful evidence
requires paired current HTML/JSON reports with executed, successful assertions;
failure artifacts are diagnostic only.

Check identity includes private HMAC-bound `.env` inputs, and configured maximum
age limits reuse. Effective installed-package probing, full deployment readiness,
independent-review provenance and complete requirement coverage are still tracked
separately in the active change. No production deployment is authorized by this
documentation or by passing local tests.
