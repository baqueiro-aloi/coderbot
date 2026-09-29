"""Check VM path rewriting and portable copies without connecting to SSH."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_vm_env import prepare


ROOT = Path(__file__).resolve().parent.parent


class VmCopy(unittest.TestCase):
    def test_prepare_rewrites_only_paths_and_preserves_local_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, target = base / "app", base / "target"
            app.mkdir()
            target.mkdir()
            source, output = app / ".env", base / "converted"
            original = (f"# local setup\nCODEBOT_REPO_PATH={target}\n"
                        f"CODEBOT_DATA_DIR={app}/data\n"
                        f"CODEBOT_E2E_COMPOSE_FILE={target}/e2e/docker-compose.yml\n"
                        "GH_TOKEN=private-token\nUNKNOWN_EXTRA=keep\n")
            source.write_text(original)
            prepare(source, output, app, target, Path("/home/azureuser/codebot/target"))
            self.assertEqual(source.read_text(), original)
            self.assertIn("CODEBOT_REPO_PATH=/home/azureuser/codebot/target\n", output.read_text())
            self.assertIn("CODEBOT_DATA_DIR=/app/data\n", output.read_text())
            self.assertIn("CODEBOT_E2E_COMPOSE_FILE=/home/azureuser/codebot/target/e2e/docker-compose.yml\n",
                          output.read_text())
            self.assertIn("GH_TOKEN=private-token\nUNKNOWN_EXTRA=keep\n", output.read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_external_absolute_override_fails_before_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / ".env"
            source.write_text("CODEBOT_REPO_PATH=/local/target\nCLAUDE_CONFIG_PATH=/Users/person/.claude.json\n")
            with self.assertRaisesRegex(ValueError, "CLAUDE_CONFIG_PATH"):
                prepare(source, base / "output", base, Path("/local/target"),
                        Path("/home/azureuser/codebot/target"))
            self.assertFalse((base / "output").exists())

    def test_script_copies_sources_and_npmrc_but_not_macos_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app, target, home, bin_dir = (base / part for part in ("app", "target", "vm", "bin"))
            local_home = base / "mac-home"
            for folder in (app / "scripts", target, home, bin_dir, local_home):
                folder.mkdir(parents=True)
            (local_home / ".npmrc").write_text("//registry.test/:_authToken=private-token\n")
            (home / ".npmrc").write_text("//registry.test/:_authToken=previous-token\n")
            for name in ("__init__.py", "setup_env.py", "setup_catalog.py", "prepare_vm_env.py",
                         "sync-to-vm.sh"):
                shutil.copy2(ROOT / "scripts" / name, app / "scripts" / name)
            original = f"# original\nCODEBOT_REPO_PATH={target}\nGH_TOKEN=private-token\n"
            (app / ".env").write_text(original)
            (app / "data").mkdir()
            (app / "data" / "token.json").write_text("token")
            (app / "data" / "heartbeat").write_text("old Mac heartbeat")
            (app / "data/opencode/cache/opencode/bin").mkdir(parents=True)
            (app / "data/opencode/cache/opencode/bin/rg").write_text("arm64 executable")
            (app / "data/opencode/data/opencode").mkdir(parents=True)
            (app / "data/opencode/data/opencode/session.json").write_text("durable session")
            (target / "node_modules").mkdir()
            (target / "node_modules" / "index.js").write_text("module")
            (target / ".cache/ms-playwright").mkdir(parents=True)
            (target / ".cache/ms-playwright" / "chromium").write_text("arm64 browser")
            (app / ".venv").mkdir()
            (app / ".venv" / "python").write_text("arm64 python")
            subprocess.run(["git", "init", "-q", str(target)], check=True)
            (bin_dir / "ssh").write_text("""#!/usr/bin/env python3
import os, pathlib, shutil, sys
home = pathlib.Path(os.environ['FAKE_VM_HOME'])
cmd = sys.argv[-1]
if cmd.startswith('printf '):
    sys.stdout.write(str(home))
elif cmd.startswith('if [ -e '):
    if (home / 'codebot/app/.env.local').exists():
        sys.exit(1)
elif cmd.startswith('mkdir -p "$HOME/codebot/app/data" && sudo -n chown '):
    (home / 'ownership-command').write_text(cmd)
elif cmd.startswith('mkdir '):
    (home / 'codebot/app').mkdir(parents=True, exist_ok=True)
    (home / 'codebot/target').mkdir(parents=True, exist_ok=True)
elif cmd.startswith('cp -p '):
    shutil.copy2(home / 'codebot/app/.env', home / 'codebot/app/.env.local')
elif cmd.startswith('if [ -f '):
    npmrc = home / '.npmrc'
    if npmrc.exists() and not (home / '.npmrc.before-codebot').exists():
        shutil.copy2(npmrc, home / '.npmrc.before-codebot')
        (home / '.npmrc.before-codebot').chmod(0o600)
elif cmd.startswith('chmod '):
    (home / '.npmrc').chmod(0o600)
else:
    sys.exit('Unexpected ssh command: ' + cmd)
""")
            (bin_dir / "rsync").write_text("""#!/usr/bin/env python3
import os, pathlib, shutil, sys
source = pathlib.Path(sys.argv[-2])
dest = sys.argv[-1].split(':', 1)[1].replace('~', os.environ['FAKE_VM_HOME'], 1)
target = pathlib.Path(dest)
if source.is_dir():
    ignored = ['node_modules', '.venv', 'venv', 'ms-playwright', 'heartbeat']
    if '--exclude=/data/' in sys.argv:
        ignored += ['data', '.env', '.env.*']
    def ignore(directory, names):
        skipped = shutil.ignore_patterns(*ignored)(directory, names)
        if ('--exclude=/data/opencode/cache/' in sys.argv and
                pathlib.Path(directory) == source / 'data/opencode'):
            skipped.add('cache')
        return skipped
    shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True,
                    ignore=ignore)
else:
    shutil.copy2(source, target)
""")
            (bin_dir / "ssh").chmod(0o755)
            (bin_dir / "rsync").chmod(0o755)
            result = subprocess.run(["bash", str(app / "scripts/sync-to-vm.sh"),
                                     "azureuser@74.235.122.91"], cwd=app, text=True,
                                    capture_output=True, timeout=30,
                                    env=os.environ | {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                                                      "HOME": str(local_home),
                                                      "FAKE_VM_HOME": str(home)})
            self.assertEqual(result.returncode, 0, result.stderr)
            copied = home / "codebot/app"
            self.assertEqual((copied / ".env.local").read_text(), original)
            self.assertIn(f"CODEBOT_REPO_PATH={home}/codebot/target\n", (copied / ".env").read_text())
            self.assertEqual((app / ".env").read_text(), original)
            self.assertTrue((home / "codebot/target/.git").exists())
            self.assertFalse((home / "codebot/target/node_modules").exists())
            self.assertFalse((home / "codebot/target/.cache/ms-playwright").exists())
            self.assertFalse((copied / ".venv").exists())
            self.assertTrue((copied / "data/token.json").exists())
            self.assertFalse((copied / "data/heartbeat").exists())
            self.assertFalse((copied / "data/opencode/cache/opencode/bin/rg").exists())
            self.assertEqual((copied / "data/opencode/data/opencode/session.json").read_text(),
                             "durable session")
            ownership = (home / "ownership-command").read_text()
            self.assertIn('501:501 "$HOME/codebot/app/data" "$HOME/codebot/target"', ownership)
            self.assertNotIn('"$HOME/codebot/app" ', ownership)
            self.assertEqual((home / ".npmrc").read_text(), (local_home / ".npmrc").read_text())
            self.assertEqual((home / ".npmrc.before-codebot").read_text(),
                             "//registry.test/:_authToken=previous-token\n")
            self.assertEqual((home / ".npmrc.before-codebot").stat().st_mode & 0o777, 0o600)
            self.assertEqual((home / ".npmrc").stat().st_mode & 0o777, 0o600)
            self.assertNotIn("private-token", result.stdout)
            again = subprocess.run(["bash", str(app / "scripts/sync-to-vm.sh"),
                                    "azureuser@74.235.122.91"], cwd=app, text=True,
                                   capture_output=True, timeout=30,
                                   env=os.environ | {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                                                     "HOME": str(local_home),
                                                     "FAKE_VM_HOME": str(home)})
            self.assertNotEqual(again.returncode, 0)  # protect the first .env.local backup
            self.assertEqual((copied / ".env.local").read_text(), original)
            (copied / "data/state.json").write_text('{"state":"WAIT_REPLY"}')
            (app / "data/state.json").write_text('{"state":"IDLE"}')
            (app / "data/token.json").write_text("different-local-token")
            (app / ".env").write_text("GH_TOKEN=changed-local-value\n")
            (app / "src").mkdir()
            (app / "src/marker.py").write_text("updated code\n")
            update = subprocess.run(["bash", str(app / "scripts/sync-to-vm.sh"),
                                     "azureuser@74.235.122.91", "--code-only"], cwd=app,
                                    text=True, capture_output=True, timeout=30,
                                    env=os.environ | {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                                                      "HOME": str(local_home),
                                                      "FAKE_VM_HOME": str(home)})
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertEqual((copied / "src/marker.py").read_text(), "updated code\n")
            self.assertEqual((copied / "data/state.json").read_text(), '{"state":"WAIT_REPLY"}')
            self.assertEqual((copied / "data/token.json").read_text(), "token")
            self.assertEqual((copied / ".env.local").read_text(), original)
            self.assertIn(f"CODEBOT_REPO_PATH={home}/codebot/target\n", (copied / ".env").read_text())
            self.assertTrue((home / "codebot/target/.git").exists())


if __name__ == "__main__":
    unittest.main()
