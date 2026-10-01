import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"task_source": Mock(), "gdoc_client": Mock(), "gmail_client": Mock()}):
    import main
from execution_store import ExecutionStore
import feedback
import replanning


class ReplanningLifecycle(unittest.TestCase):
    def test_archived_feature_revision_has_package_and_requires_approval(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            archive = "openspec/changes/archive/2026-10-01-models"
            old = repo / archive
            old.mkdir(parents=True)
            (old / "design.md").write_text("Historical design")
            database = ExecutionStore(repo / "data/db")
            state = {"state": "WAIT_MERGE", "item": "Models", "slug": "models", "branch": "feature",
                     "archive_path": archive, "pr_url": "https://example/pr/1", "session_id": "session"}
            row = feedback.receive(database, state, repo, "message", "Add model selector")
            replanning.begin(state, row)
            def replan(session, prompt):
                change = repo / "openspec/changes" / state["slug"]
                (change / "specs/models").mkdir(parents=True)
                for name in ("proposal.md", "design.md", "tasks.md"):
                    (change / name).write_text("## Revision\nModel selector\n")
                (change / "specs/models/spec.md").write_text("### Requirement: Model selector\nSelect models.\n")
                return SimpleNamespace(session_id="session", output="Add persistent model selection", question=None, attachments=[])
            with patch.object(main.config, "REPO_PATH", repo), \
                 patch.object(main.config, "DATA_DIR", repo / "data"), \
                 patch.object(main.phase_checkpoint, "store", return_value=database), \
                 patch.object(main.agent_runner, "resume", side_effect=replan), \
                 patch.object(main, "git", return_value=""), patch.object(main, "_run_checked"), patch.object(main, "save_state"), patch.object(main, "trail"), \
                 patch.object(main.gmail_client, "deliver", return_value={"thread_id": "thread", "complete": True}) as deliver:
                main.do_replan(state)
                self.assertEqual(state["state"], "WAIT_APPROVAL")
                package = deliver.call_args.args[4][0]
                self.assertIn("Model selector", package.read_text())
                self.assertEqual((old / "design.md").read_text(), "Historical design")
                self.assertEqual(state["pr_url"], "https://example/pr/1")
                main.do_approval_reply(state, "approved")
                self.assertEqual(state["state"], "IMPLEMENTING")
                self.assertNotIn("archive_path", state)
                self.assertEqual(state["replan"]["original_archive"], archive)
