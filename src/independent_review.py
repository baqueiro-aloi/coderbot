"""Controller-launched separate review session, bound to reviewed content."""
import json

from evidence_delivery import implementation_snapshot as snapshot


def run(state, repo, store, runner):
    before = snapshot(repo)
    parent = state.get('session_id')
    result = runner('Independently review the current task implementation read-only. '
        'Do not modify files, run paid calls, deploy or delegate. Inspect actual code/tests and '
        'approved OpenSpec artifacts. Return only JSON {"findings":[{"severity":"critical|important|minor",'
        '"location":"path:line","problem":"...","fix":"..."}]}. Task: '
        + str(state.get('item', '')), contract=False)
    value = json.loads(result.output)
    findings = value.get('findings') if isinstance(value, dict) else None
    if (not isinstance(result.session_id, str) or not result.session_id or result.session_id == parent
            or snapshot(repo) != before or not isinstance(findings, list)):
        raise ValueError('Independent review session or snapshot not established')
    for finding in findings:
        if (not isinstance(finding, dict) or finding.get('severity') not in ('critical', 'important', 'minor')
                or any(not isinstance(finding.get(key), str) or not finding[key].strip()
                       for key in ('location', 'problem', 'fix'))):
            raise ValueError('Independent review findings malformed')
    receipt_id = store.put('checkpoint', task_id=store.task_identity(state, repo), status='complete',
        data={'kind': 'independent_review', 'session_id': result.session_id, 'parent_session_id': parent,
              'snapshot': before, 'findings': findings})
    return {'receipt_id': receipt_id, 'session_id': result.session_id, 'snapshot': before,
            'findings': findings, 'status': 'fail' if any(f['severity'] in ('critical', 'important')
                                                       for f in findings) else 'pass'}


def valid(state, repo, store):
    review = state.get('independent_review_receipt', {})
    row = store.get('checkpoint', review.get('receipt_id')) if review.get('receipt_id') else None
    return bool(row and row['status'] == 'complete'
        and row['task_id'] == store.task_identity(state, repo)
        and row['data'].get('kind') == 'independent_review'
        and row['data'].get('session_id') != state.get('session_id')
        and row['data'].get('snapshot') == snapshot(repo)
        and not any(f['severity'] in ('critical', 'important') for f in row['data'].get('findings', [])))
