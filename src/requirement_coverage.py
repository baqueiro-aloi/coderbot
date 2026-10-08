"""Requirement coverage from actual controller receipts, never free-form claims."""
from pathlib import Path

import check_plan
import validation_overrides
import verification_ledger
from execution_identity import snapshot


def evaluate(state, repo, store, report):
    inventory = verification_ledger.requirements(repo, state)
    plan = {check.id: check for check in check_plan.discover(repo)}
    for entry in state.get('reported_check_plan', []):
        check = check_plan.Check(**entry)
        plan.setdefault(check.id, check)
    task = store.task_identity(state, repo)
    rows = []
    for requirement in inventory:
        scenarios = requirement['scenarios']
        relevant = [check for check in plan.values() if requirement['id'] in check.requirements]
        covered, receipts, exceptions = set(), [], []
        for check in relevant:
            outcome = next((value for value in report.get('checks', []) if value.get('check') == check.id), None)
            if not outcome:
                continue
            receipt = store.get('check_run', outcome.get('run_id')) if outcome.get('run_id') else None
            actual = receipt['data'].get('result', {}) if receipt else {}
            proven = (receipt and receipt['task_id'] == task and receipt['status'] == 'complete'
                and actual.get('status') == 'pass' and actual.get('identity') == outcome.get('identity')
                and actual.get('content') == snapshot(repo, check.inputs)
                and actual.get('check') == check.id)
            exception = validation_overrides.applicable(state, check)
            if proven:
                receipts.append(receipt['id'])
                covered.update(check.scenarios)
            elif exception and outcome.get('status') == 'not_run':
                exceptions.append(exception['id'])
                covered.update(check.scenarios)
        missing = [scenario for scenario in scenarios if scenario not in covered]
        rows.append({'id': requirement['id'], 'title': requirement['title'],
            'status': 'covered' if (receipts or exceptions) and not missing else 'missing',
            'receipts': receipts, 'exceptions': exceptions, 'missing_scenarios': missing})
    return {'snapshot': snapshot(repo), 'requirements': rows,
            'status': 'pass' if rows and all(row['status'] == 'covered' for row in rows) else 'indeterminate'}
