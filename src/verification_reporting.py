"""Separate execution results, accepted omissions and deployment facts."""
START = '<!-- codebot:validation:start -->'
END = '<!-- codebot:validation:end -->'


def summary(state):
    report = state.get('final_check_report', {})
    lines = ['## Validation evidence', '', '| Check | Kind | Execution | Gate |', '| --- | --- | --- | --- |']
    for row in report.get('checks', []):
        clean = lambda value: str(value).replace('|', '\\|').replace('\n', ' ')
        lines.append('| ' + ' | '.join(clean(value) for value in (
            row.get('check', '?'), row.get('kind', 'unknown'), row.get('status', 'not_run'),
            row.get('gate', {}).get('status', 'indeterminate'))) + ' |')
        exception = row.get('exception')
        if exception:
            lines.append('Accepted omission: ' + clean(row.get('check')) + '; decision '
                         + clean(exception.get('message_id', 'legacy/unverified')) + '; reason '
                         + clean(exception.get('reason', 'not recorded')) + '.')
    if not report.get('checks'):
        lines.append('No controller check results recorded; validation not established.')
    lines.extend(['', 'Local checks, upstream checks and postdeployment checks are distinct evidence.',
                  'Omissions are not passes. Implementation does not establish deployed/readiness status.',
                  'Deployment: ' + state.get('release_status', 'not verified; no deployment receipt') + '.'])
    return '\n'.join(lines)


def update_body(body, state):
    if body.count(START) != body.count(END) or body.count(START) > 1:
        raise ValueError('Bot validation section is malformed; preserve human PR body')
    block = START + '\n' + summary(state) + '\n' + END
    if START in body:
        before, remainder = body.split(START, 1)
        _, after = remainder.split(END, 1)
        return before + block + after
    return body + '\n\n' + block
