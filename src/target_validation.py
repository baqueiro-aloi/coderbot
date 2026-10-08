"""Strict offline target-validation contracts for integration fixtures."""
from pathlib import Path


_CAPABILITIES = {'list', 'inference', 'tools', 'streaming', 'write'}


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
                    or not isinstance(entry.get('parameters'), list)):
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
