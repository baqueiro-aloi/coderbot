"""Approved-scope blocking explains exact changes without weakening approval."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import proposal_package
import turns
import scope_bookkeeping
import check_plan


class ScopeBookkeepingTests(unittest.TestCase):
    def test_result_only_inputs_are_repaired_without_trusting_results(self):
        text = 'CHECK_PLAN: {"version":1,"checks":[{"id":"x","argv":["true"],"cwd":".","inputs":{"result":"passed"}}]}'
        checks = check_plan.reported(text)
        self.assertEqual(checks[0].inputs, ["*"])
        self.assertIsNone(check_plan.reported_error(text))
        self.assertIsNotNone(check_plan.reported_error(text.replace('"result":"passed"', '"env":{"X":"secret"}')))

    def test_repair_appendix_is_relocated_but_existing_intent_edits_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            change = root / "openspec/changes/help"
            (change / "specs/api").mkdir(parents=True)
            for name in ("proposal.md", "design.md", "specs/api/spec.md"):
                (change / name).write_text("Original\n")
            tasks = change / "tasks.md"
            tasks.write_text("## Tasks\n- [ ] 1.1 Help\n")
            files = proposal_package.collect_directory(change)
            state = {"slug": "help", "approved_scope_fingerprint": proposal_package.scope_fingerprint(files)}
            before = scope_bookkeeping.capture(state, root)
            tasks.write_text("## Tasks\n- [x] 1.1 Help\n\n## Repair\n- [x] 6.1 Reporter fix\n")
            self.assertTrue(scope_bookkeeping.finish(state, root, before))
            self.assertEqual(tasks.read_text(), "## Tasks\n- [x] 1.1 Help\n")
            self.assertIn("6.1 Reporter fix", (change / "execution-log.md").read_text())
            tasks.write_text("## Tasks\n- [ ] 1.1 Different feature\n")
            self.assertFalse(scope_bookkeeping.finish(state, root, before))
            self.assertIn("Different feature", tasks.read_text())

    def test_turn_guidance_preserves_approved_intent(self):
        text = turns.request({"approved_scope_fingerprint": "approved", "item": "Help"}, "IMPLEMENTING")
        self.assertIn("execution-log.md", text)
        self.assertIn("do not add tasks", text)
        self.assertNotIn("Approved intent is frozen", turns.request({"item": "Help"}, "PROPOSING"))

    def test_scope_block_includes_exact_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            change = root / "openspec/changes/help"
            (change / "specs/api").mkdir(parents=True)
            for name in ("proposal.md", "design.md", "tasks.md", "specs/api/spec.md"):
                (change / name).write_text("Original\n")
            files = proposal_package.collect_directory(change)
            snapshot = proposal_package.save_snapshot(root / "data", "help", files)
            state = {"slug": "help", "proposal_snapshot": str(snapshot),
                     "approved_scope_fingerprint": proposal_package.scope_fingerprint(files)}
            (change / "tasks.md").write_text("Original\n- [ ] 6.1 Repair reporter\n")
            with patch.object(main.config, "REPO_PATH", root), patch.object(main, "_verification_blocked") as blocked:
                self.assertTrue(main._scope_drift(state))
            self.assertIn("+" + "- [ ] 6.1 Repair reporter", blocked.call_args.args[2])
            self.assertIn("author not established", blocked.call_args.args[2])
