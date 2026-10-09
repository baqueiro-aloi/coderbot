"""Strict offline target-validation contracts for integration fixtures."""
from pathlib import Path


_CAPABILITIES = {'list', 'inference', 'tools', 'streaming', 'write'}
_AUTH = {'none', 'bearer', 'api_key'}


def load(repo, path='e2e/codebot-targets.json'):
    root = Path(repo).resolve()
    contract = root / path
    if not contract.is_file():
        return None
    import json
    return validate(json.loads(contract.read_text()), root)


def validate(value, root):
    root = Path(root).resolve()
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('targets'), list):
        raise ValueError('Invalid target validation contract')
    ids, targets = set(), []
    for target in value['targets']:
        if not isinstance(target, dict) or not isinstance(target.get('id'), str) or not target['id'] or target['id'] in ids:
            raise ValueError('Target requires a unique id')
        ids.add(target['id'])
        matrix = target.get('matrix')
        if not isinstance(matrix, list) or not matrix:
            raise ValueError('Target requires a capability matrix')
        seen = set()
        for entry in matrix:
            if (not isinstance(entry, dict) or entry.get('capability') not in _CAPABILITIES
                    or entry['capability'] in seen or not isinstance(entry.get('route'), str)
                    or not entry['route'].startswith('/') or not isinstance(entry.get('auth'), str)
                    or entry['auth'] not in _AUTH or not isinstance(entry.get('parameters'), list)
                    or len(set(entry['parameters'])) != len(entry['parameters'])
                    or any(not isinstance(parameter, str) or not parameter for parameter in entry['parameters'])):
                raise ValueError('Invalid target capability route/auth/parameters')
            seen.add(entry['capability'])
        fixtures = target.get('fixtures', [])
        if not isinstance(fixtures, list):
            raise ValueError('Target fixtures must be a list')
        for fixture in fixtures:
            source = fixture.get('source') if isinstance(fixture, dict) else None
            file = root / fixture.get('path', '') if isinstance(fixture, dict) else root
            if (not isinstance(source, str) or not source.startswith('https://') or not file.is_file()
                    or not file.resolve().is_relative_to(root)):
                raise ValueError('Fixture needs an in-repository path and real-source URL')
        targets.append(target)
    return {'version': 1, 'targets': targets}


def invocation(contract, target_id, capability, *, route, headers, payload, transport):
    """Validate an effective SDK/proxy request before its runner may send it."""
    targets = {target['id']: target for target in contract['targets']}
    target = targets.get(target_id)
    entry = next((item for item in target.get('matrix', []) if item['capability'] == capability), None) if target else None
    if not entry or route != entry['route']:
        raise ValueError('Unknown target capability or incompatible route')
    if not isinstance(headers, dict) or not isinstance(payload, dict) or not isinstance(transport, dict):
        raise ValueError('Invocation must use structured headers, payload and transport')
    lower = {str(key).lower(): value for key, value in headers.items()}
    auth = [name for name in ('authorization', 'x-api-key', 'api-key') if lower.get(name)]
    expected = entry['auth']
    if (expected == 'none' and auth) or (expected == 'bearer' and auth != ['authorization']) or (
            expected == 'api_key' and len(auth) != 1 or len(auth) > 1):
        raise ValueError('Duplicate or incompatible authentication')
    if set(payload) - set(entry['parameters']):
        raise ValueError('Invocation contains undeclared or discarded parameters')
    if transport.get('effective_route') != route or not isinstance(transport.get('isolation_id'), str) or not transport['isolation_id']:
        raise ValueError('SDK/proxy effective route and isolated transport are required')
    return {'target': target_id, 'capability': capability, 'route': route,
            'parameters': sorted(payload), 'isolation_id': transport['isolation_id']}
