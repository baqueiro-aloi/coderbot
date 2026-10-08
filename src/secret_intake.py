"""Trusted channel boundary: replace secret links before general persistence.

Only a controller-bound pending credential request can consume a link. A
durable private 'started' receipt prevents blind retry after remote consumption.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import fcntl

import config
from check_plan import Check
from private_secrets import PrivateSecrets, SecretUnavailable
import secret_safety


LINK = re.compile(r'https?://[^\s<>]+\?[^\s<>]*#[^\s<>]+')


def _private():
    return PrivateSecrets(config.DATA_DIR / 'private-secrets')


def _name(kind, identity):
    return _private().directory / (kind + '-' + hashlib.sha256(identity.encode()).hexdigest() + '.json')


def _write(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def bind(thread, task_id, request, plan):
    if not thread:
        return
    _write(_name('context', thread), {'version': 1, 'task_id': task_id, 'request': request,
        'plan': [check.to_dict() for check in plan], 'expires': time.time() + 86400})


def _read(path):
    # PrivateSecrets checks owner/permissions/no symlinks and bounded file size.
    return _private()._read(path)


def bindings(task_id, check):
    from validation_overrides import scope
    result = []
    for path in _private().directory.glob('intake-*.json'):
        try:
            receipt = _read(path)
            if (receipt.get('state') == 'complete' and receipt.get('task_id') == task_id
                    and time.time() < receipt.get('expires', 0)):
                result.extend(receipt.get('handles', {}).get(scope(check), []))
        except SecretUnavailable:
            continue
    return result


def provision_reference(reference, thread, message_id):
    """Bind an existing private handle; never resolve arbitrary filesystem paths."""
    private = _private()
    context = _read(_name('context', thread))
    if not time.time() < context['expires']:
        raise SecretUnavailable('Private decision expired')
    plan = {entry['id']: Check(**entry) for entry in context['plan']}
    selected = [plan[identity] for identity in context['request']['check_ids']]
    receipt = {'version': 1, 'state': 'complete', 'task_id': context['task_id'],
               'handles': {}, 'expires': context['expires']}
    from validation_overrides import scope
    for check in selected:
        # A reference does not authorize copying values into a different scope.
        private.resolve(reference, task_id=context['task_id'], check=check)
        receipt['handles'][scope(check)] = [reference]
    _write(_name('intake', message_id), receipt)


def sanitize(text, thread, message_id):
    reference = re.fullmatch(r'\s*SECRET_REFERENCE:\s*([0-9a-f]{32})\s*', text)
    if reference:
        try:
            provision_reference(reference[1], thread, message_id)
            return 'Provisioned secret reference accepted; spending authorization remains separate.'
        except Exception:
            return 'Provisioned secret reference rejected; verify exact scope or continue without credentials.'
    if not LINK.search(text):
        return secret_safety.redact(text)
    for match in LINK.finditer(text):
        secret_safety.register(match.group())
    # Serialize consumption across socket/controller threads and processes.
    try:
        path = _private().directory / 'intake.lock'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return _sanitize(text, thread, message_id)
    except Exception:
        return secret_safety.redact(text) + '\nPrivate intake unavailable; use a new reference or continue without credentials.'


def _sanitize(text, thread, message_id):
    """No raw full link or plaintext escapes this function, even on failure."""
    matches = list(LINK.finditer(text))
    if not matches:
        return secret_safety.redact(text)
    for match in matches:
        secret_safety.register(match.group())
    if len(matches) != 1:
        return secret_safety.redact(text) + '\nPrivate intake rejected: send one link per credential decision.'
    url = matches[0].group().rstrip('.,)')
    path = _name('intake', message_id)
    try:
        if path.exists():
            receipt = _read(path)
            # Crash after storing the only required handle is recoverable
            # without ever fetching the link a second time.
            if receipt.get('state') == 'started' and receipt.get('handles'):
                context = _read(_name('context', thread))
                from validation_overrides import scope
                selected = [Check(**entry) for entry in context['plan']
                            if entry['id'] in context['request']['check_ids']]
                if all(scope(check) in receipt['handles'] for check in selected):
                    for check in selected:
                        for handle in receipt['handles'][scope(check)]:
                            _private().resolve(handle, task_id=context['task_id'], check=check)
                    receipt['state'] = 'complete'
                    _write(path, receipt)
            status = ('Credential securely received.' if receipt.get('state') == 'complete'
                      else 'Private intake interrupted or failed; provide a new link, or continue without credentials.')
            return secret_safety.redact(text) + '\n' + status
        context = _read(_name('context', thread))
        request = context['request']
        if not time.time() < context['expires'] or len(request['env_keys']) != 1:
            raise SecretUnavailable('Private decision is expired or requires separate bindings')
        instances = json.loads(os.environ.get('CODEBOT_PRIVATEBIN_INSTANCES', '[]'))
        if not isinstance(instances, list) or not instances:
            raise SecretUnavailable('No trusted PrivateBin instance configured')
        from privatebin_receiver import link, receive
        link(url, instances)  # Validate before recording a consumption attempt.
        receipt = {'version': 1, 'state': 'started', 'task_id': context['task_id'], 'handles': {},
                   'expires': time.time() + 86400}
        _write(path, receipt)
        plan = {entry['id']: Check(**entry) for entry in context['plan']}
        selected = [plan[identity] for identity in request['check_ids']]
        key = request['env_keys'][0]
        private = _private()
        first = selected[0]
        handle = receive(url, instances, private, task_id=context['task_id'], check=first, env_key=key)
        # Persist the first handle immediately after receipt; later failures must
        # never re-consume the remote paste.
        from validation_overrides import scope
        receipt['handles'][scope(first)] = [handle]
        _write(path, receipt)
        _, value = private.resolve(handle, task_id=context['task_id'], check=first)
        for check in selected[1:]:
            receipt['handles'][scope(check)] = [private.provision(value, task_id=context['task_id'], check=check, env_key=key)]
            _write(path, receipt)
        receipt['state'] = 'complete'
        _write(path, receipt)
        return secret_safety.redact(text) + '\nCredential securely received; paid operations still require separate authorization.'
    except Exception:
        return secret_safety.redact(text) + '\nPrivate intake unavailable or rejected; provision a new reference/link or continue without credentials.'
