"""A backend payload missing its collection is a transient MalformedPayload, never an empty backlog."""
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

import config
import jira_client as jira
import github_projects_client as ghp
from task_text import MalformedPayload, require_list

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main


def _gdoc_client():
    with patch.dict(sys.modules, {"googleapiclient": MagicMock(),
                                  "googleapiclient.discovery": MagicMock(),
                                  "googleapiclient.errors": MagicMock(),
                                  "google": MagicMock(), "google.auth": MagicMock(),
                                  "google.auth.transport": MagicMock(),
                                  "google.auth.transport.requests": MagicMock(),
                                  "google_auth": MagicMock()}):
        import gdoc_client
        return gdoc_client


class RequireList(unittest.TestCase):
    def test_lists_pass_through_and_everything_else_is_malformed(self):
        self.assertEqual(require_list({"issues": []}, "issues", "x"), [])
        self.assertEqual(require_list({"issues": [1]}, "issues", "x"), [1])
        for payload in ({}, {"issues": None}, {"issues": "oops"}, {"issues": {}}, None, "text"):
            with self.subTest(payload=payload), self.assertRaises(MalformedPayload):
                require_list(payload, "issues", "x")

    def test_is_a_runtime_error_and_classified_transient(self):
        error = MalformedPayload("x")
        self.assertIsInstance(error, RuntimeError)
        self.assertTrue(main._is_transient_network_error(error))
        self.assertFalse(main._is_transient_network_error(RuntimeError("x")))


class Jira(unittest.TestCase):
    def test_search_without_issues_list_raises(self):
        with patch.object(jira, "_request", return_value={"isLast": True}):
            with self.assertRaisesRegex(MalformedPayload, "issues"):
                jira._search("project = X")
        with patch.object(jira, "_request", return_value={"issues": None, "isLast": True}):
            with self.assertRaises(MalformedPayload):
                jira._search("project = X")
        with patch.object(jira, "_request", return_value={"issues": [], "isLast": True}):
            self.assertEqual(jira._search("project = X"), [])

    def test_validate_tolerates_a_malformed_search_payload(self):
        def request(method, path, body=None):
            if path.endswith("/statuses"):
                return [{"statuses": [{"name": n} for n in ("To Do", "In Progress", "Review", "Done")]}]
            if path == "/search/jql":
                return {"isLast": True}  # no "issues"
            return {}
        with patch.multiple(config, JIRA_PICK_LABEL="codebot", JIRA_PROJECT_KEY="TEST",
                            JIRA_PICK_STATUS="To Do", JIRA_ACTIVE_STATUS="In Progress",
                            JIRA_REVIEW_STATUS="Review", JIRA_DONE_STATUS="Done"), \
                patch.object(jira, "_request", side_effect=request), \
                self.assertLogs(jira.log, "WARNING") as logs:
            jira.validate()  # must not raise
        self.assertTrue(any("unexpected payload" in line for line in logs.output))


class GitHubProjects(unittest.TestCase):
    def _items_with(self, data):
        with patch.object(ghp, "_project", return_value={"id": "P"}), \
                patch.object(ghp, "_graphql", return_value=data):
            return ghp._items()

    def test_missing_node_or_nodes_is_malformed_but_empty_board_is_empty(self):
        for data in ({}, {"node": None}, {"node": {"items": None}},
                     {"node": {"items": {"pageInfo": {}}}},
                     {"node": {"items": {"pageInfo": {}, "nodes": None}}}):
            with self.subTest(data=data), self.assertRaises(MalformedPayload):
                self._items_with(data)
        self.assertEqual(self._items_with({"node": {"items": {"pageInfo": {}, "nodes": []}}}), [])


class GoogleDoc(unittest.TestCase):
    def test_document_without_body_content_is_malformed(self):
        gdoc_client = _gdoc_client()
        for document in ({}, {"body": None}, {"body": {}}, {"body": {"content": None}}):
            with self.subTest(document=document), self.assertRaises(MalformedPayload):
                gdoc_client._tasks(document)
        self.assertEqual(gdoc_client._tasks({"body": {"content": []}}), [])


if __name__ == "__main__":
    unittest.main()
