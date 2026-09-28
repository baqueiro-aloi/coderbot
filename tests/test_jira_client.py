"""Jira v3 HTTP contract and enhanced JQL pagination, without live credentials."""
import io
import copy
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

import config
import jira_client as jira


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class JiraHttp(unittest.TestCase):
    def setUp(self):
        site = patch.object(config, "JIRA_URL", "https://test.atlassian.net")
        site.start()
        self.addCleanup(site.stop)

    def test_basic_auth_url_timeout_and_json(self):
        with patch.multiple(config, JIRA_URL="https://test.atlassian.net",
                            JIRA_EMAIL="bot@example.com", JIRA_API_TOKEN="secret"), \
             patch.object(jira.urllib.request, "urlopen", return_value=Response(b'{"ok":true}')) as send:
            self.assertEqual(jira._request("POST", "/search/jql", {"jql": "project = TEST"}),
                             {"ok": True})
        request, = send.call_args.args
        self.assertEqual(request.full_url, "https://test.atlassian.net/rest/api/3/search/jql")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(send.call_args.kwargs["timeout"], 60)
        self.assertIn("Basic ", request.get_header("Authorization"))

    def test_http_error_is_actionable(self):
        error = urllib.error.HTTPError("url", 401, "Unauthorized", Message(), io.BytesIO(b"invalid token"))
        with patch.object(jira.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401: invalid token"):
                jira._request("GET", "/myself")

    def test_search_uses_next_page_tokens(self):
        pages = [{"issues": [{"id": "1"}], "nextPageToken": "next", "isLast": False},
                 {"issues": [{"id": "2"}], "isLast": True}]
        with patch.object(jira, "_request", side_effect=pages) as send:
            self.assertEqual([i["id"] for i in jira._search('project = "TEST"')], ["1", "2"])
        self.assertEqual(send.call_args_list[0].args[:2], ("POST", "/search/jql"))
        self.assertEqual(send.call_args_list[1].args[2]["nextPageToken"], "next")

    def test_adf_description_preserves_nested_lists_and_links(self):
        def paragraph(text, href=None):
            node = {"type": "text", "text": text}
            if href:
                node["marks"] = [{"type": "link", "attrs": {"href": href}}]
            return {"type": "paragraph", "content": [node]}

        content = {"type": "doc", "content": [
            paragraph("Fix UI"),
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [
                    paragraph("See spec", "https://example.test/spec"),
                    {"type": "bulletList", "content": [{"type": "listItem", "content": [
                        paragraph("nested")]}]}]}
            ]}]}
        rendered = jira.adf_text(content)
        self.assertIn("Fix UI", rendered)
        self.assertIn("- See spec (https://example.test/spec)", rendered)
        self.assertIn("  - nested", rendered)

    def test_image_attachment_downloads_only_from_jira_and_tolerates_failures(self):
        issue = {"fields": {"attachment": [
            {"id": "2", "filename": "shot.png", "mimeType": "image/png",
             "content": "https://test.atlassian.net/rest/api/3/attachment/content/2"},
            {"id": "3", "filename": "report.txt", "mimeType": "text/plain"},
            {"id": "4", "filename": "foreign.png", "mimeType": "image/png",
             "content": "https://example.test/image"}]}}
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(jira, "IMAGES_DIR", Path(tmp)), \
             patch.object(jira.urllib.request, "urlopen", return_value=Response(b"image")):
            files = jira._download_images(issue)
            self.assertEqual(len(files), 1)
            self.assertEqual(Path(files[0]).read_bytes(), b"image")

    def test_pending_filters_status_labels_and_recovers_own_claim(self):
        def issue(number, summary, status, labels=()):
            return {"id": str(number), "key": f"TEST-{number}", "fields": {
                "summary": summary, "status": {"name": status}, "labels": list(labels),
                "description": {"type": "doc", "content": []}, "attachment": []}}

        with patch.multiple(config, JIRA_PROJECT_KEY="TEST", JIRA_PICK_STATUS="Ready",
                            JIRA_DONE_STATUS="Done", JIRA_URL="https://test.atlassian.net"), \
             patch.object(jira, "_search", side_effect=[
                 [issue(1, "Codebot[3] fix", "Ready"),
                  issue(2, "other", "Ready", ["codebot-claim-other-abc"]),
                  issue(3, "different status", "Backlog")],
                 [issue(4, "mine", "In progress", [jira.claim_label()]),
                  issue(1, "Codebot[3] fix", "Ready")]]):
            items = jira.list_pending_items()
        self.assertEqual([(i["key"], i["claimed_by_me"], i["priority"]) for i in items],
                         [("TEST-1", False, 3), ("TEST-4", True, None)])
        self.assertEqual(items[0]["url"], "https://test.atlassian.net/browse/TEST-1")


class JiraIssueActions(unittest.TestCase):
    def setUp(self):
        self.site = patch.multiple(config, JIRA_URL="https://test.atlassian.net",
                                   JIRA_PROJECT_KEY="TEST", JIRA_PICK_STATUS="Ready",
                                   JIRA_ACTIVE_STATUS="In progress", JIRA_REVIEW_STATUS="In review",
                                   JIRA_DONE_STATUS="Done")
        self.site.start()
        self.addCleanup(self.site.stop)
        self.issue = {"id": "101", "key": "TEST-1", "fields": {
            "summary": "fix it", "status": {"name": "Ready"},
            "labels": ["existing"], "attachment": []}}
        self.calls = []
        self.rival = None

        def request(method, path, payload=None):
            self.calls.append((method, path, payload))
            if path == "/issue/101" and method == "PUT":
                for operation in payload["update"]["labels"]:
                    if "add" in operation:
                        self.issue["fields"]["labels"].append(operation["add"])
                        if self.rival:
                            self.issue["fields"]["labels"].append(self.rival)
                            self.rival = None
                    else:
                        self.issue["fields"]["labels"].remove(operation["remove"])
                return {}
            if path.startswith("/issue/101?fields="):
                return copy.deepcopy(self.issue)
            if path == "/issue/101/transitions" and method == "GET":
                return {"transitions": [{"id": "1", "to": {"name": "Ready"}},
                                        {"id": "2", "to": {"name": "In progress"}},
                                        {"id": "3", "to": {"name": "In review"}},
                                        {"id": "4", "to": {"name": "Done"}}]}
            if path == "/issue/101/transitions" and method == "POST":
                mapping = {"1": "Ready", "2": "In progress", "3": "In review", "4": "Done"}
                self.issue["fields"]["status"] = {"name": mapping[payload["transition"]["id"]]}
                return {}
            raise AssertionError((method, path, payload))

        self.request_patch = patch.object(jira, "_request", side_effect=request)
        self.request_patch.start()
        self.addCleanup(self.request_patch.stop)

    def test_direct_read_refuses_stale_search_claim_from_other_bot(self):
        self.issue["fields"]["labels"].append(
            f"codebot-claim-{config.INSTANCE_ID}-{'f' * 32}")
        if self.issue["fields"]["labels"][-1] == jira.claim_label():
            self.issue["fields"]["labels"][-1] = f"codebot-claim-{config.INSTANCE_ID}-{'e' * 32}"
        self.assertFalse(jira.claim_task("fix it", "101"))
        self.assertFalse(any(c[0] == "PUT" for c in self.calls))

    def test_claim_verifies_label_and_transitions_then_holds_and_completes(self):
        self.assertTrue(jira.claim_task("fix it", "101"))
        self.assertEqual(self.issue["fields"]["status"]["name"], "In progress")
        self.assertTrue(jira.hold_task("fix it", "101"))
        self.assertEqual(set(self.issue["fields"]["labels"]), {"existing", jira.hold_label()})
        self.assertTrue(jira.unhold_task("fix it", "101"))
        self.assertTrue(jira.claim_task("fix it", "101"))
        self.assertTrue(jira.mark_done("fix it", "101"))
        self.assertEqual(self.issue["fields"]["status"]["name"], "Done")
        self.assertEqual(self.issue["fields"]["labels"], ["existing"])

    def test_losing_label_race_removes_only_own_label(self):
        self.rival = "codebot-claim-other-abcdef"
        self.assertFalse(jira.claim_task("fix it", "101"))
        self.assertEqual(set(self.issue["fields"]["labels"]),
                         {"existing", "codebot-claim-other-abcdef"})
        self.assertEqual(self.issue["fields"]["status"]["name"], "Ready")

    def test_unavailable_transition_reports_issue_and_target(self):
        with patch.object(jira, "_request", return_value={"transitions": []}):
            with self.assertRaisesRegex(RuntimeError, "TEST-1 cannot transition.*Done"):
                jira._transition(copy.deepcopy(self.issue), "Done")

    def test_abort_returns_to_ready_without_dropping_other_labels(self):
        self.assertTrue(jira.claim_task("fix it", "101"))
        self.assertTrue(jira.unclaim_task("fix it", "101"))
        self.assertEqual(self.issue["fields"]["status"]["name"], "Ready")
        self.assertEqual(self.issue["fields"]["labels"], ["existing"])

    def test_startup_checks_configured_status_names(self):
        with patch.object(jira, "_request", side_effect=[{"accountId": "bot"},
                 {"key": "TEST"}, [{"statuses": [{"name": "Ready"},
                 {"name": "In progress"}, {"name": "In review"}]}]]):
            with self.assertRaisesRegex(RuntimeError, "CODEBOT_JIRA_DONE_STATUS.*Done"):
                jira.validate()

    def test_pr_moves_to_review_and_posts_link_as_adf_comment(self):
        self.assertTrue(jira.claim_task("fix it", "101"))
        # The fake request method records the comment, though this test needs
        # only the contract of the outgoing payload.
        with patch.object(jira, "_comment") as comment:
            jira.note_pr("fix it", "101", "https://github.com/acme/repo/pull/7")
        self.assertEqual(self.issue["fields"]["status"]["name"], "In review")
        comment.assert_called_once()
        self.assertIn("pull/7", comment.call_args.args[1])
        self.assertEqual(jira._adf("hello\nworld")["content"][1]["content"][0]["text"],
                         "world")

    def test_seed_checks_all_statuses_and_transitions_new_issue(self):
        with patch.object(jira, "_search", return_value=[{
                "fields": {"summary": "old", "description": jira._adf("existing task")}}]):
            self.assertFalse(jira.ensure_item("existing task"))
        with patch.object(jira, "_search", return_value=[]), \
             patch.object(jira, "_request", return_value={"id": "101"}) as send, \
             patch.object(jira, "_issue", return_value=copy.deepcopy(self.issue)), \
             patch.object(jira, "_transition") as transition:
            self.assertTrue(jira.ensure_item("new task"))
        self.assertEqual(send.call_args.args[:2], ("POST", "/issue"))
        self.assertEqual(send.call_args.args[2]["fields"]["summary"], "new task")
        transition.assert_called_once()


if __name__ == "__main__":
    unittest.main()
