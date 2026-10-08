"""Read actual installed runtime dependencies, not declared manifests alone."""
import json
from pathlib import Path
import shutil
import subprocess

import operations


def installed(argv, cwd):
    executable = argv[0]
    resolved = shutil.which(executable) if '/' not in executable else str(Path(cwd) / executable)
    result = {'launcher': str(resolved or 'unavailable'), 'verified': True}
    name = Path(executable).name
    if name.startswith('python') or name in ('pytest',):
        python = executable if name.startswith('python') else str(Path(resolved).parent / 'python') if resolved else 'python3'
        script = ("import importlib.metadata as m,json,sys; print(json.dumps({'prefix':sys.prefix,"
                  "'packages':sorted((d.metadata['Name'],d.version) for d in m.distributions())}))")
        try:
            probe = operations.run([python, '-c', script], cwd=cwd, timeout=20, kind='probe')
            value = json.loads(probe.stdout)
            if probe.returncode or not isinstance(value, dict) or not isinstance(value.get('packages'), list):
                raise ValueError()
            result['python'] = value
        except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired):
            result['verified'] = False
    if name in ('node', 'npm', 'npx'):
        try:
            probe = operations.run(['npm', 'ls', '--all', '--json', '--ignore-scripts'],
                                   cwd=cwd, timeout=20, kind='probe')
            value = json.loads(probe.stdout)
            if not isinstance(value, dict) or probe.returncode:
                raise ValueError()
            result['node'] = value
        except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired):
            result['verified'] = False
    return result
