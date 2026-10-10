"""Existing PR handoffs publish task commits and verify the actual GitHub head."""
import json
import unittest
from unittest.mock import patch, Mock
import sys

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main


class PRPublication(unittest.TestCase):
    def state(self):
        return {"pr_url": "https://github.com/org/repo/pull/111", "branch": "task"}

    def info(self, **changes):
        return dict({"state": "OPEN", "headRefName": "task", "headRefOid": "a" * 40,
                     "baseRefName": main.config.BASE_BRANCH, "isCrossRepository": False}, **changes)

    def test_existing_pr_publishes_head_without_force_then_confirms_remote(self):
        state = self.state()
        def command(argv):
            if argv[0] == "gh":
                return json.dumps(self.info(headRefOid="b" * 40 if published else "a" * 40))
            return ""
        published = False
        def git(*args):
            nonlocal published
            if args[0] == "push":
                published = True
            return "b" * 40 if args[0] == "rev-parse" else ""
        with patch.object(main, "_run_checked", side_effect=command), patch.object(main, "git", side_effect=git) as run:
            main._publish_existing_pr(state)
            main._verify_pr_publication(state)
        run.assert_any_call("push", "origin", "HEAD:refs/heads/task")
        self.assertEqual(state["delivered_sha"], "b" * 40)
        self.assertFalse(any("--force" in call.args for call in run.call_args_list))

    def test_wrong_target_closed_or_fork_pr_never_pushes(self):
        for changes in ({"state": "CLOSED"}, {"headRefName": "other"},
                        {"baseRefName": "other-base"}, {"isCrossRepository": True}):
            with self.subTest(changes=changes), patch.object(main, "_run_checked", return_value=json.dumps(self.info(**changes))), \
                 patch.object(main, "git") as git:
                with self.assertRaisesRegex(RuntimeError, "publication target"):
                    main._publish_existing_pr(self.state())
                git.assert_not_called()

    def test_remote_branch_mapping_is_respected(self):
        state = dict(self.state(), remote_branch="original-task")
        with patch.object(main, "_run_checked", side_effect=[json.dumps(self.info(headRefName="original-task")), ""]), \
             patch.object(main, "git", return_value="") as git:
            main._publish_existing_pr(state)
        git.assert_any_call("push", "origin", "HEAD:refs/heads/original-task")

    def test_push_rejection_and_head_mismatch_never_claim_delivery(self):
        state = self.state()
        with patch.object(main, "_run_checked", return_value=json.dumps(self.info())), \
             patch.object(main, "git", side_effect=lambda *args: (_ for _ in ()).throw(RuntimeError("rejected")) if args[0] == "push" else ""):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                main._publish_existing_pr(state)
        self.assertNotIn("delivered_sha", state)
        with patch.object(main, "_run_checked", return_value=json.dumps(self.info())), \
             patch.object(main, "git", return_value="b" * 40):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                main._verify_pr_publication(state)
        self.assertNotIn("delivered_sha", state)
