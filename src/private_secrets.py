"""Private, expiring credentials scoped to an exact task/check operation.

This store is controller-only. Never expose its records, paths or plaintext to
agent prompts, general SQLite, attachments or argv. It does not resolve links.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

import secret_safety
import validation_overrides


class SecretUnavailable(ValueError):
    pass


class PrivateSecrets:
    def __init__(self, directory, *, clock=time.time):
        self.directory = Path(directory)
        self.clock = clock
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise SecretUnavailable('Private secret directory is not owner-controlled')
        self.directory.chmod(0o700)

    def _path(self, handle):
        if not isinstance(handle, str) or not re.fullmatch(r'[0-9a-f]{32}', handle):
            raise SecretUnavailable('Invalid private handle')
        return self.directory / (handle + '.json')

    def _read(self, path):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise SecretUnavailable('Private secret permissions invalid')
                if info.st_size > 65536:
                    raise SecretUnavailable('Private secret record too large')
                value = json.load(source)
        except (OSError, ValueError, TypeError):
            raise SecretUnavailable('Private secret missing or invalid; provision again') from None
        if not isinstance(value, dict) or value.get('version') != 1:
            raise SecretUnavailable('Private secret record unsupported')
        return value

    def provision(self, value, *, task_id, check, env_key, ttl=3600):
        if (not isinstance(value, str) or not value or len(value.encode()) > 32768
                or '\x00' in value or env_key not in check.env_keys
                or not re.fullmatch(r'[A-Z][A-Z0-9_]*', env_key)
                or not isinstance(task_id, str) or not task_id
                or type(ttl) not in (int, float) or not 0 < ttl <= 86400):
            raise SecretUnavailable('Invalid private provisioning scope or lifetime')
        secret_safety.register(value)
        handle = uuid.uuid4().hex
        record = {'version': 1, 'task': hashlib.sha256(task_id.encode()).hexdigest(),
                  'scope': validation_overrides.scope(check), 'env_key': env_key,
                  'expires': self.clock() + ttl, 'value': value}
        path = self._path(handle)
        # Exclusive final filename + fsync: interrupted records are rejected;
        # callers must retain a handle only after this method succeeds.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(record, output)
            output.flush()
            os.fsync(output.fileno())
        directory_fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return handle

    def resolve(self, handle, *, task_id, check):
        path = self._path(handle)
        record = self._read(path)
        if type(record.get('expires')) not in (int, float) or not self.clock() < record['expires']:
            self.revoke(handle)
            raise SecretUnavailable('Private secret expired; provision again or continue without it')
        if (record.get('task') != hashlib.sha256(task_id.encode()).hexdigest()
                or record.get('scope') != validation_overrides.scope(check)
                or record.get('env_key') not in check.env_keys
                or not isinstance(record.get('value'), str) or not record['value']):
            raise SecretUnavailable('Private secret operation scope mismatch')
        secret_safety.register(record['value'])
        return record['env_key'], record['value']

    def revoke(self, handle):
        self._path(handle).unlink(missing_ok=True)

    def cleanup(self):
        for path in self.directory.glob('*.json'):
            try:
                record = self._read(path)
                # Intake receipts retain consumed-message identity for a day;
                # deleting them on an expired credential must not re-fetch it.
                expired = not self.clock() < record.get('expires', 0)
            except (SecretUnavailable, TypeError):
                expired = True
            if expired:
                path.unlink(missing_ok=True)

    @contextmanager
    def environment(self, handles, *, task_id, check, environ=None):
        env = dict(os.environ if environ is None else environ)
        injected = {}
        for handle in handles:
            key, value = self.resolve(handle, task_id=task_id, check=check)
            if key in injected:
                raise SecretUnavailable('Duplicate credential binding')
            injected[key] = value
        env.update(injected)
        try:
            yield env
        finally:
            for key in injected:
                env.pop(key, None)
            injected.clear()
