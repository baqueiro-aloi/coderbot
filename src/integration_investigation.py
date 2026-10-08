"""Versioned integration contracts; source claims are not live-run receipts."""
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Integration inventory requires ' + label)
    return value


def _paths(values, repo):
    if not isinstance(values, list) or not values:
        raise ValueError('Internal integration requires implementation and consumer paths')
    root = Path(repo).resolve()
    for raw in values:
        _text(raw, 'path')
        path = root / raw
        if Path(raw).is_absolute() or '..' in Path(raw).parts or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Integration reference must be a real repository file')


def validate(value, repo):
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('integrations'), list):
        raise ValueError('Invalid integration inventory version or entries')
    ids = set()
    for entry in value['integrations']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid integration entry')
        identity = _text(entry.get('id'), 'id')
        if identity in ids or entry.get('kind') not in ('internal', 'external'):
            raise ValueError('Duplicate or invalid integration')
        ids.add(identity)
        versions = entry.get('versions')
        if not isinstance(versions, dict):
            raise ValueError('Integration requires effective versions')
        for name in ('declared', 'installed', 'deployment'):
            _text(versions.get(name), name + ' version')
        sources = entry.get('sources')
        if not isinstance(sources, list) or not sources:
            raise ValueError('Integration requires consulted sources')
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError('Invalid source')
            url = urlsplit(_text(source.get('url'), 'source URL'))
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('Source requires public HTTPS reference')
            try:
                date.fromisoformat(source.get('consulted_at', ''))
            except (ValueError, TypeError):
                raise ValueError('Source requires consultation date') from None
            _text(source.get('evidence'), 'consulted contract evidence')
            if source.get('version') not in (versions['installed'], versions['deployment']):
                raise ValueError('Source version does not match effective integration version')
        contract = entry.get('contract')
        if not isinstance(contract, dict):
            raise ValueError('Integration requires contract')
        for name in ('method', 'route', 'auth', 'isolation', 'request', 'response'):
            _text(contract.get(name), 'contract ' + name)
        for name in ('errors', 'capabilities'):
            values = contract.get(name)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError('Invalid contract ' + name)
        if entry['kind'] == 'internal':
            _paths(entry.get('implementation'), repo)
            _paths(entry.get('consumers'), repo)
        assumptions = entry.get('assumptions')
        if not isinstance(assumptions, list):
            raise ValueError('Integration requires explicit assumptions inventory')
        for assumption in assumptions:
            if (not isinstance(assumption, dict) or type(assumption.get('material')) is not bool
                    or assumption.get('status') not in ('confirmed', 'pending', 'contradicted')):
                raise ValueError('Invalid integration assumption')
            for name in ('claim', 'impact', 'next_action'):
                _text(assumption.get(name), 'assumption ' + name)
        if not isinstance(entry.get('checks'), list) or any(not isinstance(c, str) or not c for c in entry['checks']):
            raise ValueError('Integration requires validation check ids')
    return value


def blockers(inventory):
    return [entry['id'] + ': ' + assumption['claim'] + '; ' + assumption['next_action']
            for entry in inventory['integrations'] for assumption in entry['assumptions']
            if assumption['material'] and assumption['status'] != 'confirmed']


def reported(output):
    entries = [line[len('INTEGRATION_INVENTORY:'):].strip() for line in output.splitlines()
               if line.startswith('INTEGRATION_INVENTORY:')]
    if len(entries) > 1:
        raise ValueError('Expected one integration inventory')
    return json.loads(entries[0]) if entries else None
