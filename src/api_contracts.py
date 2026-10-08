"""Required collection and cursor contracts: missing is never empty."""


def collection(value, name):
    items = value.get(name) if isinstance(value, dict) else None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError('API missing or malformed required collection: ' + name)
    return items


def next_cursor(page, seen):
    if not isinstance(page, dict) or type(page.get('hasNextPage')) is not bool:
        raise ValueError('API pagination completion unknown')
    if not page['hasNextPage']:
        return None
    cursor = page.get('endCursor')
    if not isinstance(cursor, str) or not cursor or cursor in seen:
        raise ValueError('API pagination cursor missing or repeated')
    seen.add(cursor)
    return cursor
