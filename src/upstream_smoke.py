"""Bounded, explicitly authorized upstream smoke execution."""
import credential_requests
import checks


def run(state, repo, store, check, request, *, secret_handles=()):
    if check.kind != 'upstream' or check.timeout > 120 or not check.external_dependencies:
        raise ValueError('Smoke requires a bounded upstream check with declared dependency')
    credential_requests.validate(request, [check])
    if check.id not in request['check_ids'] or 'synthetic' not in request['effects'].lower():
        raise ValueError('Smoke request must name this check and synthetic effects')
    if request['paid'] and not credential_requests.authorized(request, state):
        raise PermissionError('Paid upstream smoke lacks explicit budget authorization')
    if not secret_handles and check.env_keys:
        raise PermissionError('Upstream smoke lacks its scoped credential handle')
    result = checks.execute(check, repo, store, store.task_identity(state, repo), secret_handles=secret_handles)
    return {**result, 'evidence_class': 'upstream', 'synthetic': True,
            'authorized_budget': bool(not request['paid'] or credential_requests.authorized(request, state))}
