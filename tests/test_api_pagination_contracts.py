import unittest
from unittest.mock import patch

import jira_client
import api_contracts


class PaginationContractTests(unittest.TestCase):
    def test_graphql_missing_completion_and_cyclic_cursor_are_unknown(self):
        seen = set()
        self.assertEqual(api_contracts.next_cursor({'hasNextPage': True, 'endCursor': 'a'}, seen), 'a')
        for page in ({}, {'hasNextPage': 'false'}, {'hasNextPage': True},
                     {'hasNextPage': True, 'endCursor': 'a'}):
            with self.subTest(page=page), self.assertRaises(ValueError):
                api_contracts.next_cursor(page, seen)
    def test_missing_collection_is_not_empty_backlog(self):
        for value in ({}, {'issues': None}, {'issues': {}}, {'issues': [None]},
                      {'issues': [], 'isLast': 'true'}):
            with self.subTest(value=value), patch.object(jira_client, '_request', return_value=value), self.assertRaises(RuntimeError):
                jira_client._search('project=TEST')

    def test_nonconsecutive_cursor_cycle_rejected(self):
        pages = [{'issues': [], 'isLast': False, 'nextPageToken': cursor} for cursor in ('a', 'b', 'a')]
        with patch.object(jira_client, '_request', side_effect=pages) as request, self.assertRaises(RuntimeError):
            jira_client._search('project=TEST')
        self.assertEqual(request.call_count, 3)

    def test_next_page_without_cursor_cannot_claim_completion(self):
        with patch.object(jira_client, '_request', return_value={'issues': [], 'isLast': False}), self.assertRaises(RuntimeError):
            jira_client._search('project=TEST')

    def test_real_empty_page_and_all_pages(self):
        pages = [{'issues': [{'id': '1'}], 'isLast': False, 'nextPageToken': 'a'},
                 {'issues': [{'id': '2'}], 'isLast': True}]
        with patch.object(jira_client, '_request', side_effect=pages):
            self.assertEqual([row['id'] for row in jira_client._search('project=TEST')], ['1', '2'])
