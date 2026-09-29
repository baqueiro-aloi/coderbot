"""Setup's VM action delegates to the copier and verifies optional restart."""
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import setup
from scripts.setup_env import EnvFile


class VmAction(unittest.TestCase):
    def test_rejects_invalid_hosts_without_running_commands(self):
        with patch.object(setup.subprocess, "run") as run:
            for host in ("", "example.com", "-bad@host", "user@host;touch /tmp/x"):
                with self.subTest(host=host), self.assertRaisesRegex(ValueError, "user@host"):
                    setup.sync_to_vm(host, code_only=True, restart=True)
        run.assert_not_called()

    def test_update_code_only_does_not_restart_or_touch_env(self):
        with patch.object(setup.subprocess, "run") as run:
            result = setup.sync_to_vm("azureuser@74.235.122.91", code_only=True, restart=False)
        run.assert_called_once_with(
            ["bash", str(setup.ROOT / "scripts/sync-to-vm.sh"),
             "azureuser@74.235.122.91", "--code-only"], cwd=setup.ROOT, check=True)
        self.assertIn("Restart", result)

    def test_initial_copy_then_recreate_and_check_health(self):
        with patch.object(setup.subprocess, "run") as run:
            result = setup.sync_to_vm("azureuser@74.235.122.91", code_only=False, restart=True)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0],
                         ["bash", str(setup.ROOT / "scripts/sync-to-vm.sh"),
                          "azureuser@74.235.122.91"])
        restart = run.call_args_list[1]
        self.assertEqual(restart.args[0],
                         ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                          "azureuser@74.235.122.91", "sh -eu"])
        self.assertIn("--force-recreate codebot", restart.kwargs["input"])
        self.assertIn(".State.Health.Status", restart.kwargs["input"])
        self.assertNotIn("azureuser@74.235.122.91", restart.kwargs["input"])
        self.assertIn("healthy", result)

    def test_copy_failure_does_not_restart(self):
        failure = subprocess.CalledProcessError(12, ["bash", "sync-to-vm.sh"])
        with patch.object(setup.subprocess, "run", side_effect=failure) as run:
            with self.assertRaisesRegex(RuntimeError, "VM copy failed"):
                setup.sync_to_vm("azureuser@74.235.122.91", code_only=True, restart=True)
        run.assert_called_once()

    def test_restart_failure_reports_successful_copy_separately(self):
        failure = subprocess.CalledProcessError(1, ["ssh", "sh -eu"])
        with patch.object(setup.subprocess, "run", side_effect=[None, failure]) as run:
            with self.assertRaisesRegex(RuntimeError, "Files copied, but VM restart/health check failed"):
                setup.sync_to_vm("azureuser@74.235.122.91", code_only=True, restart=True)
        self.assertEqual(run.call_count, 2)

    def test_remote_health_script_succeeds_only_for_healthy_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            app = home / "codebot/app"
            bin_dir = Path(tmp) / "bin"
            app.mkdir(parents=True)
            bin_dir.mkdir()
            (app / "docker-compose.yml").write_text("services: {}\n")
            docker = bin_dir / "docker"
            docker.write_text("#!/usr/bin/env python3\n"
                              "import os, sys\n"
                              "if 'ps' in sys.argv: print('container123')\n"
                              "elif 'inspect' in sys.argv: print(os.environ['FAKE_HEALTH'])\n")
            docker.chmod(0o755)
            for health, expected in (("healthy", 0), ("unhealthy", 1)):
                with self.subTest(health=health):
                    proc = subprocess.run(["sh", "-eu"], input=setup._VM_RESTART_AND_CHECK,
                                          text=True, capture_output=True, timeout=5,
                                          env=os.environ | {"HOME": str(home), "FAKE_HEALTH": health,
                                                            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
                    self.assertEqual(proc.returncode, expected, proc.stderr)
                    self.assertIn(health, proc.stdout if expected == 0 else proc.stderr)

    def test_text_menu_offers_update_and_requires_confirmation_for_initial_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("UNKNOWN=unchanged\n")
            answers = iter(["v", "azureuser@74.235.122.91", "u", "y", "q"])
            with patch("builtins.input", side_effect=lambda prompt: next(answers)), \
                 patch.object(setup, "sync_to_vm", return_value="VM healthy") as sync, \
                 redirect_stdout(StringIO()) as output:
                setup.text_setup(EnvFile(path))
            sync.assert_called_once_with("azureuser@74.235.122.91", code_only=True,
                                         restart=True)
            self.assertIn("VM healthy", output.getvalue())
            self.assertEqual(path.read_text(), "UNKNOWN=unchanged\n")
            answers = iter(["v", "azureuser@74.235.122.91", "i", "n", "q"])
            with patch("builtins.input", side_effect=lambda prompt: next(answers)), \
                 patch.object(setup, "sync_to_vm") as sync, redirect_stdout(StringIO()):
                setup.text_setup(EnvFile(path))
            sync.assert_not_called()
            answers = iter(["v", "azureuser@74.235.122.91", "i", "y", "n", "q"])
            with patch("builtins.input", side_effect=lambda prompt: next(answers)), \
                 patch.object(setup, "sync_to_vm", return_value="VM copied") as sync, \
                 redirect_stdout(StringIO()):
                setup.text_setup(EnvFile(path))
            sync.assert_called_once_with("azureuser@74.235.122.91", code_only=False,
                                         restart=False)


if __name__ == "__main__":
    unittest.main()
