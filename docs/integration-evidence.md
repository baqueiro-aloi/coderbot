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

**Secret intake is opt-in.** Never send plaintext credentials. Configure
`CODEBOT_PRIVATEBIN_INSTANCES` with exact trusted HTTPS instance paths. With
the default `[]`, links are rejected and redacted, not fetched. Only a currently
bound credential decision on the same task thread can receive a link; one key
per message, protocol v2 plaintext burn-after-reading only. A provisioned
`SECRET_REFERENCE: <opaque-handle>` must already match the exact task/check.
Existing runtime credentials and continuation without keys remain alternatives.

The trusted controller can provision `PrivateSecrets` records in its private
data area (directory 0700, records 0600), returning opaque handles. Handles bind
task, exact check operation and environment name, expire within at most 24 hours,
and survive controller restart. `checks.execute(..., secret_handles=[...])`
injects them only into the selected child environment; reports are redacted and
identity uses HMAC rather than stored values. Expired/invalid records can be
cleaned without touching target work. Deletion removes the file but does not
promise secure erasure on SSDs, snapshots or backups. Do not put this private
area in the target repository, general database, outbox or model-accessible paths.
Slack sanitizes before inbox commit; email sanitizes before returning to the
controller. General history gets only a receipt description, never full link,
key or plaintext. A private consumption receipt prevents duplicate fetches;
crash before successful private persistence requests a new link, while a stored
complete scope can recover without remote consumption. Key availability does
not authorize proposed spending. Provider chat retention is outside this local
boundary: use short-lived credentials and do not expect erasure of sent messages.

PrivateBin decoder supports protocol v2 as implemented by PrivateBin 2.0.6,
using the pinned PBinCLI 0.3.7 crypto implementation only (never its CLI,
configuration, network or debug mode). Supported: plaintext formatter, no
discussion, burn-after-reading, AES-256-GCM with 128-bit tag, 16-byte IV,
8-byte salt, PBKDF2-SHA256 with 10,000–100,000 iterations, compression none or
raw deflate bounded to 32 KiB. Password-protected pastes, attachments, other
formats/protocols and unconfigured HTTPS instance paths are rejected.
Transport strips the fragment, pins public DNS addresses, disallows redirects,
requires the configured host, and bounds bytes/time. The private receiver returns
only a scoped handle. Channel intake accepts links only for bound decisions.

Sources consulted 2026-10-08:
- https://raw.githubusercontent.com/PrivateBin/PrivateBin/2.0.6/js/privatebin.js
- https://raw.githubusercontent.com/r4sas/PBinCLI/0.3.7/pbincli/format.py
- https://pypi.org/pypi/pbincli/json (latest published release 0.3.7, 2025-03-22).

Compatibility tests encrypt independently with Node WebCrypto and with the
pinned client; reject authenticated-data changes, corrupted ciphertext and
oversized decompression. No real secret or live burn-after-reading paste used.

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

## Remote review binding

Review delivery records the remote `headRefOid` and includes it in the handoff.
A later merge verifies that same remote head; unknown or changed heads require
another review handoff, including legacy tasks without a head receipt. Explicit
thread bypass does not bypass this condition. The actual GitHub CLI merge uses
`--match-head-commit` so a push racing the last read is rejected by the provider.
Reference consulted: https://cli.github.com/manual/gh_pr_merge (2026-10-08).

Docs v1 returns HTTP 400 for stale required revisions *and* invalid requests.
The client retries a rejected CAS write only after a fresh read establishes a
different revision; unchanged or unavailable revisions do not imply conflict.
Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate#WriteControl
(2026-10-08).

## Verification boundaries

Known test reporters retain executed/skipped counts. Zero tests produce
`not_run`; skipped tests remain visible. Local SDK/mocks do not demonstrate
upstream inference, tools, streaming or authorization. Newman successful evidence
requires paired current HTML/JSON reports with executed, successful assertions;
failure artifacts are diagnostic only.

Check identity includes private HMAC-bound `.env` inputs, and configured maximum
age limits reuse. Python distributions and npm's effective installed graph are
probed in the actual check environment; failed probes prevent reuse. Baseline
cache applies the same installation/configuration and remote freshness controls.
New investigated tasks require requirement/scenario coverage linked to actual
controller execution receipts or exact omissions, plus a separately launched
read-only review-session receipt. Code changes invalidate that review; moving
OpenSpec artifacts into the archive alone does not. Local snapshots do not prove
remote deployment. Full readiness and broader rollout remain active tasks.

Recovery now backs up dirty/index bytes privately before isolation and keeps
unknown work in its original checkout. Model attribution prose is advisory only.
Returning to base refuses dirty work/incomplete operations and uses normal
checkout/fast-forward only, never forced checkout, broad clean or hard reset.
Backup files can contain secrets: keep recovery-backups private and outside Git,
outbox and the target workspace. SSD/snapshot erasure is not guaranteed.

No production deployment is authorized by this documentation or passing local tests.

## Evidence terminology

`implemented` means only that a code change exists. `local` identifies a
controller-run check against the checkout. `upstream` identifies an explicitly
authorized remote check with a bounded freshness window. `deployed` identifies
a release receipt binding image digest and source SHA while preserving durable
task state. `postdeployment` needs its own functional smoke/readiness receipt;
systemd, Docker health and heartbeat are liveness only. These classes appear
separately in bot-owned PR validation sections. An accepted omission remains
`not_run`, with original decision and reason, in every class.

## Durable schema and rollout operation

`check_run` records created by the current controller carry
`result.provenance: "verified_v2"`. On database open, an older completed receipt
that has a result but lacks provenance is preserved and labelled
`legacy_unverified`; it cannot be reused as proof. Records with no result are
ordinary historical rows and are not rewritten. Legacy free-text `check_waivers`
are moved to `legacy_validation_waivers` for audit and never omit a check. A new
exception requires the version-2 exact-check receipt described above.

`scripts/rollout_performance.py` is a local-host helper, not an AWS or Azure
deployment mechanism. It requires an existing state file, a release checkout and
an already-built image. It snapshots private runtime inputs with restrictive
permissions, binds the authorized image digest and release SHA, recreates the
container without changing the original target checkout, and records an explicit
readiness plus smoke-probe receipt. Docker health, systemd and heartbeat alone
are liveness, not functional verification. A failed recreation or functional
probe restores the captured image/mount configuration; operators must review the
private backup and rollback result before retrying. No command in this project
selects a cloud account, changes IAM, provisions infrastructure or spends money.
