"""Complete offline proposal package, including nested specs and hostile Markdown."""
import tempfile
import unittest
from pathlib import Path

import proposal_package


class ProposalPackage(unittest.TestCase):
    def test_contains_all_artifacts_and_safe_clickable_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "openspec/changes/example"
            (root / "specs/nested/api").mkdir(parents=True)
            (root / "proposal.md").write_text("# Proposal\nUser-visible text\n")
            (root / "design.md").write_text("## Design\n<script>alert(1)</script>\n"
                                            "[bad](javascript:alert(2))")
            (root / "tasks.md").write_text("## Tasks\n- [ ] one task\n")
            (root / "specs/nested/api/spec.md").write_text("### Requirement: Nested\n"
                                                           "![diagram](https://example.test/a.png)")
            files = proposal_package.collect(Path(tmp), "example")
            document = proposal_package.render(files, "Review example")
        self.assertEqual(len(files), 4)
        self.assertIn('href="#doc-3-h1"', document)
        self.assertIn('specs/nested/api/spec.md', document)
        self.assertIn('User-visible text', document)
        self.assertIn('[Image: diagram]', document)
        self.assertNotIn('<script>alert', document)
        self.assertNotIn('href="javascript:', document)
        self.assertIn('type="search"', document)

    def test_missing_and_symlinked_artifacts_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "openspec/changes/example"
            (root / "specs/one").mkdir(parents=True)
            for name in ("proposal.md", "design.md", "tasks.md"):
                (root / name).write_text(name)
            (root / "specs/one/spec.md").write_text("ok")
            self.assertEqual(len(proposal_package.collect(Path(tmp), "example")), 4)
            (root / "design.md").unlink()
            with self.assertRaises(FileNotFoundError):
                proposal_package.collect(Path(tmp), "example")
            (root / "design.md").symlink_to(root / "proposal.md")
            with self.assertRaises(FileNotFoundError):
                proposal_package.collect(Path(tmp), "example")
            with self.assertRaises(ValueError):
                proposal_package.collect(Path(tmp), "../example")

    def test_immutable_bundle_and_revision_diff_track_last_sent_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, data = Path(tmp) / "repo", Path(tmp) / "data"
            root = repo / "openspec/changes/example"
            (root / "specs/api").mkdir(parents=True)
            for name in ("proposal.md", "design.md", "tasks.md"):
                (root / name).write_text(f"## {name}\nBefore\n")
            (root / "specs/api/spec.md").write_text("### Requirement: Original\nBefore\n")
            first, original = proposal_package.prepare(data, repo, "example", "bot-example", 100000)
            snapshot = proposal_package.save_snapshot(data, "bot-example", original)
            (root / "design.md").write_text("## design.md\nAfter\n")
            (root / "specs/api/spec.md").write_text("### Requirement: New\nAfter\n")
            second, updated = proposal_package.prepare(data, repo, "example", "bot-example", 100000)
            diff = proposal_package.changes(proposal_package.previous(str(snapshot)), updated)
            self.assertIn("Changed in design.md", diff)
            self.assertIn("Added in specs/api/spec.md", diff)
            self.assertIn("Removed from specs/api/spec.md", diff)
            self.assertNotEqual(first, second)
            self.assertIn("Before", first.read_text())
            self.assertIn("After", second.read_text())
            with self.assertRaisesRegex(ValueError, "attachment cap"):
                proposal_package.prepare(data, repo, "example", "bot-example", 3)
