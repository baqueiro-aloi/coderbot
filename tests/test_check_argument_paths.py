"""Check validation distinguishes script paths from opaque command arguments."""
import errno
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from check_plan import Check
from workspace_checks import HarnessBlocked
import workspace_runner


PATTERN = (
    "Test(ClassifyZip|ZipHasBankPDFs|IsMaterializableZipBucket|ContentTypeForZipBucket|"
    "DispatchZipDecompress|Prepare_tabularZipFileIds|PrepareYDispatchZip|PrepareZip_extensionesLegacy|"
    "CompleteZipDecompress|FlattenZipListerEntries|ZipListerBatchEnv|ZipListerCallback|"
    "CompleteZipLister_rechaza|CollectBankStatementIDsFromFiles|SetBankReportInclusion|"
    "UpsertZipEntries_conserva|ListAllZipEntries|ListZipEntries_NonPositive)"
)


class CheckArgumentPaths(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        self.context = SimpleNamespace(root=self.root)

    def test_long_go_test_selection_is_not_a_filename(self):
        argv = ["go", "test", "-count=1", "-v", "./pkg/workspaces/models", "-run", PATTERN]
        original = list(argv)
        workspace_runner.validate_check(self.context, Check("zip-backend", argv))
        self.assertEqual(argv, original)

    def test_long_inline_code_and_script_like_arguments_are_not_paths(self):
        for source in ("print('" + "a" * 300 + "')", "x" * 300 + ".py"):
            with self.subTest(source=source):
                workspace_runner.validate_check(self.context, Check("inline", ["python3", "-c", source]))

    def test_long_inline_cleanup_is_still_rejected(self):
        code = "echo " + "x" * 300 + "; docker volume prune; echo ignored.sh"
        with self.assertRaisesRegex(HarnessBlocked, "global destructive"):
            workspace_runner.validate_check(self.context, Check("inline", ["sh", "-c", code]))

    def test_real_script_with_spaces_is_still_inspected(self):
        (self.root / "unsafe test.py").write_text("# docker volume prune\n")
        with self.assertRaisesRegex(HarnessBlocked, "global destructive"):
            workspace_runner.validate_check(self.context, Check("script", ["python3", "unsafe test.py"]))

    def test_script_permission_errors_are_not_silently_ignored(self):
        path = self.root / "test.py"
        path.write_text("print('ok')")
        original = Path.is_file
        def probe(candidate):
            if candidate == path:
                raise PermissionError(errno.EACCES, "denied", str(path))
            return original(candidate)
        with patch.object(Path, "is_file", probe), self.assertRaises(PermissionError):
            workspace_runner.validate_check(self.context, Check("script", ["python3", "test.py"]))

    def test_delegated_cleanup_is_still_inspected(self):
        (self.root / "run.sh").write_text("./unsafe.sh\n")
        (self.root / "unsafe.sh").write_text("docker network prune\n")
        with self.assertRaisesRegex(HarnessBlocked, "global destructive"):
            workspace_runner.validate_check(self.context, Check("script", ["./run.sh"]))
