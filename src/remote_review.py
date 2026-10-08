"""GitHub head receipts; local snapshots never stand in for remote review."""
import json
import re
import subprocess


def head(pr_url, repo, timeout=60):
    result = subprocess.run(['gh', 'pr', 'view', pr_url, '--json', 'state,headRefOid'],
                            cwd=repo, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Remote PR head could not be verified')
    value = json.loads(result.stdout)
    if (not isinstance(value, dict) or value.get('state') not in ('OPEN', 'CLOSED', 'MERGED')
            or not isinstance(value.get('headRefOid'), str)
            or not re.fullmatch(r'[0-9a-f]{40}', value['headRefOid'])):
        raise ValueError('Remote PR head response invalid')
    return value


def reviewed(state, value):
    return value['state'] == 'OPEN' and state.get('reviewed_remote_sha') == value['headRefOid']


def merge_argv(pr_url, sha):
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Merge requires the reviewed remote SHA')
    return ['gh', 'pr', 'merge', pr_url, '--squash', '--match-head-commit', sha]
