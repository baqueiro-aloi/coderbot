"""Keep human conversation visible; move only technical payloads to reports."""
import json
import re


def split(body):
    """Return conversational text and whether raw technical content was removed."""
    lines = body.splitlines()
    visible = []
    removed = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith('Traceback (most recent call last)'):
            removed = True
            index += 1
            # Tracebacks/logs are technical; preserve the explicit closing action.
            while index < len(lines) and not re.match(
                    r"\s*(Reply\b|Responde\b|Decision\b|Your (?:input|decision)\b|¿)", lines[index]):
                index += 1
            continue
        if line.strip() in ('```json', '```log'):
            end = next((i for i in range(index + 1, len(lines)) if lines[i].strip() == '```'), None)
            if end is not None:
                removed = True
                index = end + 1
                continue
        # JSON may span many lines. Decode actual objects, never guess from braces
        # in ordinary prose or drop the human text following a technical object.
        if line.lstrip().startswith(('{', '[')):
            remainder = '\n'.join(lines[index:])
            leading = len(remainder) - len(remainder.lstrip())
            try:
                value, end = json.JSONDecoder().raw_decode(remainder, leading)
            except ValueError:
                pass
            else:
                if isinstance(value, (dict, list)):
                    removed = True
                    suffix = remainder[end:].lstrip('\n')
                    lines = suffix.splitlines()
                    index = 0
                    continue
        visible.append(line)
        index += 1
    return '\n'.join(visible).strip(), removed
