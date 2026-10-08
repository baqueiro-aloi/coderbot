"""Read all review-thread comments, with bounded provider cursor traversal."""
import json
import subprocess

import api_contracts


def complete(thread_id, connection, repo, timeout=60):
    comments = list(api_contracts.collection(connection, 'nodes'))
    info = connection.get('pageInfo')
    if info is None:
        # Historical fixtures/payloads predate requested pageInfo; only a short
        # page is unambiguously complete. A full page cannot certify completeness.
        if len(comments) >= 100:
            raise ValueError('Review comment pagination missing')
        return comments
    seen = set()
    cursor = api_contracts.next_cursor(info, seen)
    query = '''query($id:ID!,$cursor:String){node(id:$id){... on PullRequestReviewThread {
      comments(first:100,after:$cursor){pageInfo{hasNextPage endCursor}
        nodes{author{login __typename} body databaseId createdAt}}}}}'''
    for _ in range(1000):
        if cursor is None:
            return comments
        result = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + query,
            '-f', 'id=' + thread_id, '-f', 'cursor=' + cursor], cwd=repo,
            capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise ValueError('Review comments could not be read completely')
        value = json.loads(result.stdout)
        if value.get('errors'):
            raise ValueError('Review comments provider error')
        page = value['data']['node']['comments']
        comments.extend(api_contracts.collection(page, 'nodes'))
        cursor = api_contracts.next_cursor(page.get('pageInfo'), seen)
    raise ValueError('Review comment pagination budget exhausted')
