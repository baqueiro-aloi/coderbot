"""Backlog-doc parsing: sections, sub-bullets, images, claim markers, task identity.

Pure functions over a fake Docs payload — the Google client libs are stubbed."""
import sys
import unittest
from unittest.mock import MagicMock, patch

with patch.dict(sys.modules, {"googleapiclient": MagicMock(),
                              "googleapiclient.discovery": MagicMock(),
                              "googleapiclient.errors": MagicMock(),
                              "google": MagicMock(), "google.auth": MagicMock(),
                              "google.auth.transport": MagicMock(),
                              "google.auth.transport.requests": MagicMock(),
                              "google_auth": MagicMock()}):
    import gdoc_client

import config

SECTION = "Backlog:"


def _para(text, start, level=None, heading=False, struck=False):
    para = {"elements": [{"textRun": {"content": text + "\n",
                                      "textStyle": {"strikethrough": True} if struck else {}}}]}
    if level is not None:
        para["bullet"] = {"listId": "L1", "nestingLevel": level}
    if heading:
        para["paragraphStyle"] = {"namedStyleType": "HEADING_3"}
    return {"startIndex": start, "endIndex": start + len(text) + 1, "paragraph": para}


def _img_para(obj_id, start):
    # A pasted screenshot: its own paragraph, no text run, not a bullet.
    return {"startIndex": start, "endIndex": start + 1, "paragraph": {
        "elements": [{"inlineObjectElement": {"inlineObjectId": obj_id}}]}}


# A heading, a plain note under it, top-level bullets with nested clarifications
# (including a level-0 -> level-2 skip), inline screenshots under a bullet, a struck
# item, and a second section.
DOC = {"body": {"content": [
    _para(SECTION, 1, heading=True),
    _para("(add new improvements here)", 20),
    _para("Main information of the task.", 70, level=0),
    _img_para("kix.img1", 105),
    _para("some clarification", 110, level=1),
    _img_para("kix.img2", 135),
    _para("some other clarification", 140, level=1),
    _para("Task whose sub-bullets skip a level", 180, level=0),
    _para("deep clarification", 230, level=2),
    _para("Already done task", 260, level=0, struck=True),
    _para("Under review:", 290, heading=True),
    _para("Not ready to work on", 310, level=0),
]}}


def _task(text, **over):
    base = {"text": text, "detail": "", "struck": False, "section": SECTION,
            "images": [], "ranges": []}
    base.update(over)
    return base


class TaskGrouping(unittest.TestCase):
    def setUp(self):
        self.tasks = gdoc_client._tasks(DOC)
        self.by_text = {t["text"]: t for t in self.tasks}

    def test_sub_bullets_group_into_top_level_bullet(self):
        self.assertEqual([t["text"] for t in self.tasks],
                         ["Main information of the task.", "Task whose sub-bullets skip a level",
                          "Already done task", "Not ready to work on"])

    def test_clarifications_become_indented_detail(self):
        self.assertEqual(self.by_text["Main information of the task."]["detail"],
                         "    - some clarification\n    - some other clarification")
        self.assertEqual(self.by_text["Task whose sub-bullets skip a level"]["detail"],
                         "        - deep clarification")
        self.assertEqual(self.by_text["Already done task"]["detail"], "")

    def test_plain_paragraphs_are_not_tasks(self):
        self.assertNotIn("(add new improvements here)", self.by_text)

    def test_strike_ranges_cover_sub_bullets_but_not_images(self):
        self.assertEqual(len(self.by_text["Main information of the task."]["ranges"]), 3)
        self.assertEqual(self.by_text["Already done task"]["ranges"], [(260, 278)])

    def test_heading_ends_group(self):
        self.assertEqual(self.by_text["Not ready to work on"]["section"], "Under review:")

    def test_images_attach_to_task(self):
        self.assertEqual(self.by_text["Main information of the task."]["images"],
                         ["kix.img1", "kix.img2"])
        self.assertEqual(self.by_text["Task whose sub-bullets skip a level"]["images"], [])


class Pending(unittest.TestCase):
    def test_only_configured_section_when_set(self):
        with patch.object(config, "DOC_SECTION", SECTION):
            texts = [i["text"] for i in gdoc_client._pending(gdoc_client._tasks(DOC))]
        self.assertEqual(texts, ["Main information of the task.",
                                 "Task whose sub-bullets skip a level"])

    def test_every_section_when_unset(self):
        with patch.object(config, "DOC_SECTION", ""):
            texts = [i["text"] for i in gdoc_client._pending(gdoc_client._tasks(DOC))]
        self.assertEqual(texts, ["Main information of the task.",
                                 "Task whose sub-bullets skip a level", "Not ready to work on"])

    def test_section_match_is_whitespace_and_case_insensitive(self):
        with patch.object(config, "DOC_SECTION", "  backlog: "):
            texts = [i["text"] for i in gdoc_client._pending(gdoc_client._tasks(DOC))]
        self.assertEqual(len(texts), 2)


class ClaimMarkers(unittest.TestCase):
    def test_strip_and_parse(self):
        self.assertEqual(gdoc_client.strip_claims("Fix header [implementing: codebot2]").strip(),
                         "Fix header")
        self.assertEqual(gdoc_client.claimed_by("Task [Implementing: Bot2]"), "bot2")
        self.assertIsNone(gdoc_client.claimed_by("Task with no marker"))

    def test_foreign_claims_hidden_own_claim_flagged(self):
        tasks = [_task(f"mine [implementing: {config.INSTANCE_ID}]"),
                 _task("theirs [implementing: another-bot]"), _task("free")]
        with patch.object(config, "DOC_SECTION", SECTION):
            pend = gdoc_client._pending(tasks)
        self.assertEqual([t["text"] for t in pend], ["mine", "free"])
        self.assertTrue(pend[0]["claimed_by_me"])
        self.assertFalse(pend[1]["claimed_by_me"])

    def test_malformed_marker_reads_as_claimed(self):
        self.assertEqual(gdoc_client.claimed_by("x [implementing: ] [implementing: alpha]"), "?")
        with patch.object(config, "DOC_SECTION", SECTION):
            self.assertEqual(gdoc_client._pending([_task("half [implementing: ]")]), [])

    def test_marker_ranges_use_utf16_offsets(self):
        doc = {"body": {"content": [
            {"startIndex": 10, "endIndex": 41, "paragraph": {"elements": [
                {"startIndex": 10, "textRun": {"content": "Fix \U0001F642 "}},
                {"startIndex": 17, "textRun": {"content": "[implementing: codebot]\n"}},
            ]}}]}}
        self.assertEqual(gdoc_client._marker_ranges(doc, {"ranges": [(10, 41)]}), [(16, 40)])
        self.assertEqual(gdoc_client._marker_ranges(doc, {"ranges": [(10, 41)]}, "codebot"),
                         [(16, 40)])
        self.assertEqual(gdoc_client._marker_ranges(doc, {"ranges": [(10, 41)]}, "otherbot"), [])


class PriorityTags(unittest.TestCase):
    def test_priority_parsed_case_and_space_insensitive(self):
        self.assertEqual(gdoc_client.priority_of("Fix header Codebot[2]"), 2)
        self.assertEqual(gdoc_client.priority_of("codebot [ 10 ] first"), 10)
        self.assertIsNone(gdoc_client.priority_of("no tag here"))
        self.assertIsNone(gdoc_client.priority_of("codebot[implementing: x]"))

    def test_pending_items_carry_priority(self):
        with patch.object(config, "DOC_SECTION", SECTION):
            pend = gdoc_client._pending([_task("A Codebot[3]"), _task("B")])
        self.assertEqual([i["priority"] for i in pend], [3, None])


class TaskIdentity(unittest.TestCase):
    def test_find_task_prefers_workable_copy(self):
        doc = {"body": {"content": [
            _para(SECTION, 1, heading=True),
            _para("dup task", 20, level=0, struck=True),
            _para("dup task", 40, level=0),
            _para(f"other [implementing: {config.INSTANCE_ID}]", 60, level=0),
            _para("other", 200, level=0),
        ]}}
        self.assertEqual(gdoc_client._find_task(doc, "dup task")["ranges"][0][0], 40)
        self.assertEqual(gdoc_client._find_task(doc, "other")["ranges"][0][0], 60)

    def test_find_mine_after_bullet_edit(self):
        doc = {"body": {"content": [
            _para(SECTION, 1, heading=True),
            _para(f"renamed bullet text [implementing: {config.INSTANCE_ID}]", 20, level=0),
            _para("some other task", 300, level=0),
        ]}}
        self.assertIsNone(gdoc_client._find_task(doc, "original bullet text"))
        self.assertEqual(gdoc_client._find_mine(doc)["ranges"][0][0], 20)

    def test_find_mine_refuses_to_guess(self):
        doc = {"body": {"content": [
            _para(f"a [implementing: {config.INSTANCE_ID}]", 20, level=0),
            _para(f"b [implementing: {config.INSTANCE_ID}]", 200, level=0),
        ]}}
        self.assertIsNone(gdoc_client._find_mine(doc))


if __name__ == "__main__":
    unittest.main()
