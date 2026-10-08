# Authorized integration pilot checklist

This checklist is deliberately a runbook, not authorization. Do not execute a
remote call, provision a cloud resource, change IAM, deploy, or spend money
until the named human has approved the exact target, effects, budget and check
ids in the task thread.

## Before a pilot

1. Record a version-1 target contract in `e2e/codebot-targets.json`: route,
   auth shape, capability matrix, parameters and source-traced synthetic fixture.
2. Make the upstream smoke check use synthetic data, bounded timeout and resource
   limits. A list/auth response is not proof of inference, tools or streaming.
3. Create a version-1 credential request naming the exact env key, check ids,
   effects, paid flag and maximum currency amount. Configure only an exact
   `CODEBOT_PRIVATEBIN_INSTANCES` URL if PrivateBin is selected.
4. Obtain a separate scoped budget authorization if `paid: true`; a credential
   receipt alone is not spending authorization.
5. Decide and record one of: secure provision, `continue without key` for the
   exact named check(s), or pause. The latter two must not widen scope.

## Pilot execution and release

1. Inspect the final report: local, upstream, deployed and postdeployment remain
   separate. `not_run` and legacy receipts are not pass evidence.
2. Preserve a remote SHA review receipt and an independent-review receipt bound
   to the current snapshot before any merge decision.
3. For the local rollout helper, provide both JSON argv readiness and smoke
   probes. It rejects liveness-only success and rolls back its image/mounts on a
   failed functional receipt.
4. Confirm the original target checkout and durable state are preserved. Review
   the private rollback backup; do not add it to Git or send it to chat.

## Explicit external pending work

No real provider target, private credential, paid budget, AWS/Azure account,
IAM permission, or production deployment is configured by this repository.
Those inputs must be supplied and approved by the pilot owner. Until then, the
implementation supports local contracts and synthetic/offline regressions only.
