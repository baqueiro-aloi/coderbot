import subprocess
import tempfile
import unittest
import sys
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import verification_recovery
from execution_identity import snapshot
from execution_store import ExecutionStore

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main


class PlanRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.change = self.repo / "openspec/changes/feature"
        (self.change / "specs/capability").mkdir(parents=True)
        for name, content in {"proposal.md": "Already approved\n", "design.md": "Existing design\n",
                              "tasks.md": "- [x] 1. Implement\n", "specs/capability/spec.md": "Requirement\n"}.items():
            (self.change / name).write_text(content)
        (self.repo / "app.py").write_text("legitimate code\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "complete")
        self.sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def test_restore_backs_up_documents_and_preserves_index_code_and_head(self):
        (self.change / "tasks.md").write_text("- [x] 1. Implement\n- [ ] 10. Approve again\n")
        (self.change / "proposal.md").write_text("Invented approval gate\n")
        (self.repo / "app.py").write_text("legitimate review correction\n")
        self.git("add", "app.py", "openspec")
        (self.repo / "app.py").write_text("further legitimate correction\n")
        staged = self.git("diff", "--cached", "--binary")
        result = verification_recovery.restore(self.repo, "feature", self.sha, self.root / "data")
        backup = Path(result["backup"])
        self.assertEqual((backup / "tasks.md").read_text(), "- [x] 1. Implement\n- [ ] 10. Approve again\n")
        self.assertEqual((self.change / "tasks.md").read_text(), "- [x] 1. Implement\n")
        self.assertEqual((self.change / "proposal.md").read_text(), "Already approved\n")
        self.assertEqual((self.repo / "app.py").read_text(), "further legitimate correction\n")
        self.assertEqual(self.git("diff", "--cached", "--binary"), staged)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.sha)

    def test_incomplete_checkpoint_is_rejected_without_writes(self):
        (self.change / "tasks.md").write_text("- [ ] 1. Implement\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "incomplete")
        sha = self.git("rev-parse", "HEAD").strip()
        before = (self.change / "tasks.md").read_bytes()
        with self.assertRaisesRegex(ValueError, "completed checklist"):
            verification_recovery.restore(self.repo, "feature", sha, self.root / "data")
        self.assertEqual((self.change / "tasks.md").read_bytes(), before)
        self.assertFalse((self.root / "data").exists())

    def test_inventory_change_and_internal_backup_are_rejected(self):
        (self.change / "specs/new").mkdir()
        (self.change / "specs/new/spec.md").write_text("new user work")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            verification_recovery.restore(self.repo, "feature", self.sha, self.root / "data")
        self.assertEqual((self.change / "specs/new/spec.md").read_text(), "new user work")

    def test_guidance_is_explicit(self):
        self.assertEqual(verification_recovery.guidance("Verify existing work"), (None, "Verify existing work"))
        self.assertEqual(verification_recovery.guidance("--restore-plan 93ea27a: existing work"),
                         ("93ea27a", "existing work"))
        with self.assertRaises(ValueError):
            verification_recovery.guidance("--restore-plan main")

    def test_polluted_plan_recovery_reuses_review_and_reaches_final_checks(self):
        data = self.root / "data"
        database = ExecutionStore(data / "execution.sqlite")
        state = {"state": "WAIT_APPROVAL", "item": "feature", "slug": "feature", "session_id": "sid"}
        task_id = database.task_identity(state, self.repo)
        database.put("checkpoint", task_id=task_id, status="consumed", data={
            "phase": "INTERNAL_REVIEW", "snapshot": snapshot(self.repo),
            "output": 'INTERNAL_REVIEW: {"status":"pass","critical":0,"important":0,"tests":["focused: pass"]}'})
        (self.change / "tasks.md").write_text("- [x] 1. Implement\n- [ ] 10.1 Approve again\n- [ ] 10.2 Reconcile\n")
        output = 'QUALITY_GATE: {"status":"pass","commands":["focused: pass"],"openspec":"pass","tasks":"1/1"}'
        with patch.object(main.config, "REPO_PATH", self.repo), patch.object(main.config, "DATA_DIR", data), \
             patch.object(main.phase_checkpoint, "store", return_value=database), patch.object(main, "save_state"), \
             patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
             patch.object(main, "_run_checked", side_effect=["valid", json.dumps({"state": "all_done",
                 "progress": {"total": 1, "complete": 1, "remaining": 0}})]):
            main._request_verification(state, "--restore-plan " + self.sha)
            main._complete_verify(state, SimpleNamespace(output=output))
        self.assertEqual(state["state"], "E2E")
        self.assertNotIn("approved_proposal", state)
        self.assertTrue(Path(state["verification_plan_recovery"]["backup"]).is_dir())

    def test_internal_backup_and_symlink_are_rejected_before_replacement(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            verification_recovery.restore(self.repo, "feature", self.sha, self.repo / "data")
        self.assertFalse((self.repo / "data").exists())
        path = self.change / "proposal.md"
        path.unlink()
        outside = self.root / "outside.md"
        outside.write_text("user work")
        path.symlink_to(outside)
        with self.assertRaises((ValueError, FileNotFoundError)):
            verification_recovery.restore(self.repo, "feature", self.sha, self.root / "data")
        self.assertEqual(outside.read_text(), "user work")
