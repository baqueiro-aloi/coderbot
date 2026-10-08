import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from github_review_comments import complete


class ReviewPaginationTests(unittest.TestCase):
    def test_more_than_hundred_comments_are_read(self):
        first = {'nodes': [{'databaseId': i} for i in range(100)],
                 'pageInfo': {'hasNextPage': True, 'endCursor': 'next'}}
        response = {'data': {'node': {'comments': {'nodes': [{'databaseId': 100}],
                    'pageInfo': {'hasNextPage': False}}}}}
        with patch('github_review_comments.subprocess.run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(response))) as run:
            comments = complete('thread', first, '.')
        self.assertEqual(len(comments), 101)
        self.assertIn('cursor=next', run.call_args.args[0])

    def test_cursor_cycle_and_missing_pages_fail_closed(self):
        first = {'nodes': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'same'}}
        response = {'data': {'node': {'comments': first}}}
        with patch('github_review_comments.subprocess.run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(response))), self.assertRaises(ValueError):
            complete('thread', first, '.')
        with self.assertRaises(ValueError):
            complete('thread', {'nodes': [{}] * 100}, '.')
