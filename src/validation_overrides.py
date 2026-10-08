"""Explicit human exceptions, bound to exact semantic check contracts."""
import hashlib
import json


def scope(check):
    value = {name: getattr(check, name) for name in ('id', 'argv', 'cwd', 'kind',
        'requirements', 'scenarios', 'external_dependencies', 'env_keys')}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def authorize(state, plan, check_ids, *, message_id, author, instruction, reason):
    checks = {c.id: c for c in plan}
    if (not isinstance(check_ids, list) or not check_ids
            or any(not isinstance(i, str) or i not in checks for i in check_ids)
            or len(set(check_ids)) != len(check_ids)
            or any(not isinstance(v, str) or not v.strip() for v in (message_id, author, instruction, reason))):
        raise ValueError('Exception requires an authorized message and exact existing checks')
    receipt = {'version': 2, 'id': hashlib.sha256((message_id + json.dumps(check_ids)).encode()).hexdigest(),
        'message_id': message_id, 'author': author, 'instruction': instruction, 'reason': reason,
        'checks': {i: scope(checks[i]) for i in check_ids}, 'status': 'active'}
    values = state.setdefault('validation_overrides', [])
    existing = next((v for v in values if v['id'] == receipt['id']), None)
    if existing:
        return existing
    values.append(receipt)
    return receipt


def applicable(state, check):
    for receipt in state.get('validation_overrides', []):
        if receipt.get('version') != 2 or receipt.get('status') not in ('active', 'needs_review'):
            continue
        expected = receipt.get('checks', {}).get(check.id)
        if expected == scope(check):
            return receipt
        if expected is not None:
            # A changed operation invalidates only that binding, not unrelated
            # checks authorized by the same human message.
            receipt['status'] = 'needs_review'
            receipt.setdefault('changed_checks', {})[check.id] = scope(check)
    return None


def prompt(text, plan, question):
    from prompts import fenced
    return ('Classify only explicit human authorization to omit specified validation checks. No tools. '
        'Interpret the entire message, negations, questions, conditions and pending request. '
        'A missing key is not consent; refusal to provide a key AND request to continue authorizes '
        'only checks dependent on that key. Never authorize merge, security changes or task completion. '
        'Questions/negated omission are none; unclear scope is ambiguous. Preserve other instructions; '
        'mixed product changes or merge instructions require normal handling, not this shortcut. '
        'Return ONLY JSON {"action":"omit|none|ambiguous","check_ids":[],"reason":"",'
        '"other_instructions":""}. Select only existing ids explicitly covered by consent.\n'
        + fenced('pending question', question) + '\n'
        + fenced('available check contracts', json.dumps([c.to_dict() for c in plan])) + '\n'
        + fenced('human message', text))


def accept(state, plan, verdict, *, message_id, author, instruction):
    if (not isinstance(verdict, dict) or verdict.get('action') != 'omit'
            or verdict.get('other_instructions')):
        return False
    try:
        authorize(state, plan, verdict.get('check_ids'), message_id=message_id,
                  author=author, instruction=instruction, reason=verdict.get('reason'))
    except (ValueError, TypeError):
        return False
    return True
