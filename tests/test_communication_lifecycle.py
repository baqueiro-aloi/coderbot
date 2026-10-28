"""End-to-end communication handoff across the two supported transports."""
import json
import base64
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from email.parser import BytesParser
from email.policy import default

import gmail_client
import slack_client
import milestones
from execution_store import ExecutionStore

# Keep Markdown outside the temporary module registry. Otherwise patch.dict
# removes it after importing main, leaving proposal_package with a stale core
# whose Extension class differs from subsequently imported extension modules.
import markdown

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(),
                              "gmail_client": Mock()}):
    import main


class CommunicationLifecycle(unittest.TestCase):
    def test_repeated_state_changes_pair_real_transport_body_and_image_in_both_channels(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as root:
                directory = Path(root)
                store = ExecutionStore(directory / "db")
                state = {"item": "task", "slug": "task", "execution_task_id": "task",
                         "thread_id": "C:1" if channel == "slack" else "thread", "task_language": "Spanish"}
                api = Mock()
                api.files_upload_v2.return_value = {"files": [{"id": "accepted"}]}
                service = Mock()
                service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
                    "id": "accepted", "threadId": "thread"}
                service.users.return_value.threads.return_value.get.return_value.execute.return_value = {
                    "messages": [{"payload": {"headers": [{"name": "Message-ID", "value": "<parent@example.com>"}]}}]}
                identities = []
                with patch.object(main.config, "COMM_CHANNEL", channel), \
                     patch.object(main.config, "DATA_DIR", directory), \
                     patch.object(main.config, "REPO_PATH", directory), \
                     patch.object(main.phase_checkpoint, "store", return_value=store), \
                     patch.object(main, "save_state"), patch.object(main, "trail"), \
                     patch.object(main.agent_runner, "run") as agent, \
                     patch.object(slack_client, "web", return_value=api), \
                     patch.object(gmail_client, "_gmail", return_value=service):
                    for phase in ("VERIFYING", "IMPLEMENTING", "VERIFYING", "IMPLEMENTING", "VERIFYING"):
                        state["state"] = phase
                        main._announce_state(state)
                        self.assertTrue(state.get("last_delivery", {}).get("complete"), state.get("last_delivery"))
                        main._announce_state(state)
                        self.assertEqual(state["banner_state"], phase)
                        self.assertEqual(state["banner_stage"], milestones.state_stage(state))
                        self.assertNotIn("pending_state_notice", state)
                        identities.append(state["last_delivery"]["notification_id"])
                    agent.assert_not_called()
                self.assertEqual(len(set(identities)), 5)
                if channel == "slack":
                    api.chat_postMessage.assert_not_called()
                    self.assertEqual(api.files_upload_v2.call_count, 5)
                    names = []
                    for call in api.files_upload_v2.call_args_list:
                        self.assertIn("estoy", call.kwargs["initial_comment"])
                        self.assertIn(" · ", call.kwargs["initial_comment"])
                        names.append(call.kwargs["filename"])
                    self.assertEqual(len(set(names)), 5)
                else:
                    sends = service.users.return_value.messages.return_value.send.call_args_list
                    self.assertEqual(len(sends), 5)
                    for call in sends:
                        message = BytesParser(policy=default).parsebytes(
                            base64.urlsafe_b64decode(call.kwargs["body"]["raw"]))
                        self.assertIn("estoy", message.get_body(preferencelist=("plain",)).get_content())
                        self.assertIn("cid:codebot-progress", message.get_body(preferencelist=("html",)).get_content())
                        self.assertEqual(len([p for p in message.walk() if p.get_content_type() == "image/png"]), 1)

    def test_automatic_uncertain_notice_reuses_its_identity_without_interrupting_work(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            store = ExecutionStore(directory / "db")
            state = {"state": "VERIFYING", "item": "task", "slug": "task", "execution_task_id": "task",
                     "thread_id": "C:1", "session_id": "same-session", "approval": "preserved",
                     "audit_launches": 2, "pending_feedback": "preserved guidance"}
            api = Mock()
            api.files_upload_v2.side_effect = ConnectionError("accepted but disconnected")
            api.conversations_replies.return_value = {"messages": []}
            with patch.object(main.config, "COMM_CHANNEL", "slack"), \
                 patch.object(main.config, "DATA_DIR", directory), patch.object(main.config, "REPO_PATH", directory), \
                 patch.object(main.phase_checkpoint, "store", return_value=store), \
                 patch.object(main, "save_state"), patch.object(main, "trail"), \
                 patch.object(main.agent_runner, "run") as agent, patch.object(slack_client, "web", return_value=api):
                main._announce_state(state)
                self.assertNotIn("banner_state", state)
                pending = dict(state["pending_state_notice"])
                main._announce_state(state)
                self.assertEqual(state["pending_state_notice"], pending)
                api.files_upload_v2.assert_called_once()
                upload = api.files_upload_v2.call_args.kwargs
                api.conversations_replies.return_value = {"messages": [{"text": upload["initial_comment"],
                    "files": [{"id": "accepted", "name": upload["filename"],
                               "size": milestones.image("verifying").stat().st_size}]}]}
                main._announce_state(state)
                self.assertEqual(state["banner_state"], "VERIFYING")
                self.assertNotIn("pending_state_notice", state)
                api.files_upload_v2.assert_called_once()
                api.chat_postMessage.assert_not_called()
                agent.assert_not_called()
            self.assertEqual(state["session_id"], "same-session")
            self.assertEqual(state["approval"], "preserved")
            self.assertEqual(state["audit_launches"], 2)
            self.assertEqual(state["pending_feedback"], "preserved guidance")

    def test_review_markdown_extensions_share_the_renderer_module(self):
        self.assertIs(main.proposal_package.markdown, markdown)
        document = main.proposal_package.render({
            "design.md": "## Design\n\n```python\nprint('ok')\n```\n\n"
                         "| Check | Result |\n| --- | --- |\n| Tests | Passed |\n"
        }, "Review")
        self.assertIn("<pre><code>", document)
        self.assertIn("<table>", document)
        self.assertIn("Passed", document)

    def test_proposal_architecture_pr_and_merge_in_email_and_slack(self):
        for channel in ("email", "slack"):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp) / "repo"
                change = repo / "openspec/changes/example"
                (change / "specs/api").mkdir(parents=True)
                for name in ("proposal.md", "design.md", "tasks.md"):
                    (change / name).write_text(f"## {name}\nArchitecture\n")
                (change / "specs/api/spec.md").write_text("### Requirement: API\n")
                state = {"state": "EXPLORING", "item": "Create API", "slug": "example",
                         "branch": "bot-example", "base_sha": "a" * 40,
                         "archive_path": "openspec/changes/archive/2026-09-29-example",
                         "pr_url": "https://github.com/org/repo/pull/3",
                         "has_e2e_harness": False, "pr_summary": "Create endpoint",
                         "thread_id": "C1:1.0" if channel == "slack" else None}
                architecture = {"head": "b" * 40, "paths": ["deploy/database.tf"],
                                "planned": "## Design\nRDS", "diff": "+new DB", "complete": True}
                decision = {"decisions": [{"kind": "decision", "planned": False,
                                          "title": "Separate production RDS",
                                          "impact": "New database deployment boundary",
                                          "paths": ["deploy/database.tf"]}]}
                with patch.object(main.config, "REPO_PATH", repo), \
                     patch.object(main, "content_snapshot", return_value="fixture"), \
                     patch.object(main.config, "DATA_DIR", Path(tmp) / "data"), \
                     patch.object(main.config, "COMM_CHANNEL", channel), \
                     patch.object(main, "save_state"), patch.object(main, "trail"), \
                     patch.object(main.task_source, "mark_done", return_value=True), \
                     patch.object(main.gmail_client, "send", return_value=state["thread_id"] or "gmail-1") as send, \
                       patch.object(main.gmail_client, "deliver", side_effect=lambda s, subj, body, thread, files, **kwargs: (send(subj, body, thread, files, **{k: v for k, v in kwargs.items() if k != "identity"}), {"thread_id": thread or "gmail-1", "complete": True})[1]), \
                     patch.object(main.evidence, "record_evidence", return_value=[]), \
                     patch.object(main, "unresolved_review_threads", return_value=[]), \
                     patch.object(main.architecture_report, "collect", return_value=architecture), \
                     patch.object(main.agent_runner, "run",
                                  return_value=SimpleNamespace(output=json.dumps(decision))):
                    main.announce_milestone(state, "exploring", "Exploring")
                    state["state"] = "PROPOSING"
                    main.announce_milestone(state, "proposing", "Writing proposal")
                    main._send_proposal_review(state, "Summary")
                    main.announce_milestone(state, "implementing", "Building")
                    main.announce_milestone(state, "verifying", "Checking")
                    main.announce_milestone(state, "archiving", "Archiving")
                    main._notify_architecture(state)
                    main.finalize_pr(state)
                    self.assertEqual(state["state"], "WAIT_MERGE")
                    main._finish_task(state, "PR merged.", reset_repo=False, merged=True)
                bodies = [call.args[1] for call in send.call_args_list]
                self.assertEqual(bodies.count("Exploring"), 1)
                self.assertTrue(any("Separate production RDS" in body for body in bodies))
                self.assertTrue(any("Review cover:" in body for body in bodies))
                self.assertTrue(any(call.args[3] and call.args[3][0].suffix == ".html"
                                    for call in send.call_args_list))
                stages = [call.kwargs["progress"].stem for call in send.call_args_list
                          if call.kwargs.get("progress")]
                self.assertEqual(stages, ["exploring", "proposing", "approval", "implementing",
                                          "verifying", "archiving", "pr_review", "merged"])
                self.assertEqual(state["state"], "IDLE")
                self.assertNotIn("milestones_announced", state)
