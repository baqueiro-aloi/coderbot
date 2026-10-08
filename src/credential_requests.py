"""Early external prerequisites; possessing a key is not spending consent."""
import json
import math
import os
import re

import validation_overrides


def validate(value, plan):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Invalid credential request version')
    checks = {c.id: c for c in plan}
    for name in ('service', 'environment', 'effects', 'currency'):
        if not isinstance(value.get(name), str) or not value[name].strip():
            raise ValueError('Credential request requires ' + name)
    for name in ('env_keys', 'permissions', 'check_ids'):
        items = value.get(name)
        if not isinstance(items, list) or not items or any(not isinstance(i, str) or not i for i in items):
            raise ValueError('Credential request requires ' + name)
    if any(i not in checks for i in value['check_ids']):
        raise ValueError('Credential request references unknown checks')
    if any(not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) for key in value['env_keys']):
        raise ValueError('Credential request requires environment variable names only')
    relevant = {key for i in value['check_ids'] for key in checks[i].env_keys}
    if not set(value['env_keys']).issubset(relevant) or any(
            not set(checks[i].env_keys).intersection(value['env_keys']) for i in value['check_ids']):
        raise ValueError('Credential request keys do not match check dependencies')
    cost = value.get('max_cost')
    if type(value.get('paid')) is not bool or type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        raise ValueError('Credential request requires explicit paid flag and bounded cost')
    if not value['paid'] and cost != 0:
        raise ValueError('Nonpaid request cannot have a spending budget')
    return value


def missing(request, plan, state, environ=None):
    env = os.environ if environ is None else environ
    checks = {c.id: c for c in plan}
    active = [checks[i] for i in request['check_ids'] if not validation_overrides.applicable(state, checks[i])]
    if not active:
        return False
    active_keys = {key for check in active for key in check.env_keys}
    private_keys = set()
    if environ is None:
        import config
        from execution_store import ExecutionStore
        import secret_intake
        from private_secrets import PrivateSecrets, SecretUnavailable
        task_id = ExecutionStore(config.DATA_DIR / 'execution.sqlite').task_identity(state, config.REPO_PATH)
        private = PrivateSecrets(config.DATA_DIR / 'private-secrets')
        for check in active:
            for handle in secret_intake.bindings(task_id, check):
                try:
                    key, _ = private.resolve(handle, task_id=task_id, check=check)
                    private_keys.add(key)
                except SecretUnavailable:
                    pass
    keys_missing = any(not env.get(key, '').strip() and key not in private_keys
                       for key in request['env_keys'] if key in active_keys)
    # Spending consent must be scoped to these checks and ceiling, never global
    # tool permission or merely the availability of credentials.
    return keys_missing or request['paid'] and not authorized(request, state)


def authorized(request, state):
    """Consent is keyed to the complete proposed operation, not only key names."""
    import hashlib
    identity = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    return any(a.get('request_identity') == identity for a in state.get('external_authorizations', []))


def question(request):
    configured = os.environ.get('CODEBOT_PRIVATEBIN_INSTANCES', '[]') not in ('', '[]')
    intake_notice = ('Use only configured PrivateBin v2 plaintext burn-after-reading links; one credential per message.\n'
                     if configured else
                     'Private link intake is not enabled yet: do not send a one-time link until a supported private receiver '
                     'is configured. Use already provisioned runtime credentials in the meantime.\n')
    return (f"Validation prerequisite: {request['service']} in {request['environment']}.\n"
        f"Credential names: {', '.join(request['env_keys'])}; least permissions: {', '.join(request['permissions'])}.\n"
        f"Checks: {', '.join(request['check_ids'])}. Effects: {request['effects']}.\n"
        f"Paid operations: {request['paid']}; maximum proposed budget: {request['max_cost']} {request['currency']}. "
        "This budget is not yet authorized.\n"
        "1. Provide a provisioned secret reference or HTTPS one-time link from a supported trusted instance; "
        "explicitly authorize any proposed paid budget. Do not paste plaintext keys.\n"
        + intake_notice +
        "2. Continue without credentials: omit only the listed dependent checks and run available alternatives.\n"
        "3. Keep paused; preserve work without omitting checks.")


def reported(output):
    entries = [line[len('CREDENTIAL_REQUEST:'):].strip() for line in output.splitlines()
               if line.startswith('CREDENTIAL_REQUEST:')]
    if len(entries) > 1:
        raise ValueError('One credential decision per turn is required')
    return json.loads(entries[0]) if entries else None
