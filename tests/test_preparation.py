from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution_store import ExecutionStore
from preparation import ensure


class PreparationTests(unittest.TestCase):
    def test_reuses_verified_preparation_and_repairs_partial_install(self):
        with tempfile.TemporaryDirectory() as root:
            store = ExecutionStore(Path(root) / "db")
            spec = {"commands": [["install"]], "probes": [["probe"]], "inputs": ["lockfile"]}
            with patch("preparation.snapshot", return_value="inputs"), \
                 patch("preparation.operations.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                self.assertFalse(ensure(spec, root, store, "t")["reused"])
                self.assertTrue(ensure(spec, root, store, "t")["reused"])
                self.assertEqual(sum(c.args[0] == ["install"] for c in run.call_args_list), 1)
            with patch("preparation.snapshot", return_value="inputs"), \
                 patch("preparation.operations.run", side_effect=[subprocess.CompletedProcess([], 1, "", ""),
                     subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 0, "", "")]):
                self.assertFalse(ensure(spec, root, store, "t")["reused"])
