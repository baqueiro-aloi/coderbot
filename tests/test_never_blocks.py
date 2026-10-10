"""Invariants: hardening code must never stop the bot from starting or from progressing.

A previous hardening attempt was reverted because new gates stalled every task. These
tests pin the properties that keep that from happening again. Related invariants live
next to the code they exercise:

- redaction filter never raises/drops a record, heartbeat-style thread survives:
  tests/test_redaction.py (LogFilter)
- a failed/old-gh/unreadable-head merge falls back to the legacy path:
  tests/test_merge_pinning.py
- work preservation failing never skips the reset: tests/test_work_preservation.py
- a malformed backlog payload is transient and never exits startup:
  tests/test_malformed_payloads.py
- zero-test suites never fail the gate unless opted in, never for discovered suites:
  tests/test_empty_suites.py
"""
import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# main() refuses to start only for missing or invalid configuration. Each of these is
# deliberate; hardening work must not add new ones.
MAIN_STARTUP_EXITS = 14


def _clean_env(**extra):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
           "CODEBOT_DATA_DIR": tempfile.mkdtemp(prefix="codebot-never-blocks-")}
    env.update(extra)
    return env


def _python(code, **env):
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=_clean_env(**env),
                          capture_output=True, text=True, timeout=120)


class NeverBlocks(unittest.TestCase):
    def test_every_module_imports_with_an_empty_environment(self):
        modules = sorted(p.stem for p in SRC.glob("*.py"))
        code = ("import importlib, sys, traceback\n"
                "sys.path.insert(0, 'src')\n"
                f"for name in {modules!r}:\n"
                "    try:\n"
                "        importlib.import_module(name)\n"
                "    except BaseException as error:\n"
                "        print('IMPORT-FAILED', name, type(error).__name__, error)\n")
        result = _python(code)
        failures = [line for line in result.stdout.splitlines() if line.startswith("IMPORT-FAILED")]
        self.assertEqual(failures, [], result.stderr[-2000:])

    def test_startup_exit_points_are_unchanged(self):
        tree = ast.parse((SRC / "main.py").read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        exits = [node for node in ast.walk(main) if isinstance(node, ast.Raise) and node.exc is not None
                 and "SystemExit" in ast.unparse(node.exc)]
        self.assertEqual(len(exits), MAIN_STARTUP_EXITS,
                         "main() gained or lost a startup exit; new code must fail open instead")

    def test_log_redaction_is_wired_when_main_is_imported(self):
        token = "ghp_" + "Z" * 36
        code = ("import logging, sys\n"
                "sys.path.insert(0, 'src')\n"
                "import main, redaction\n"
                "handlers = logging.getLogger().handlers\n"
                "assert handlers, 'no root handlers'\n"
                "assert all(any(isinstance(f, redaction.Filter) for f in h.filters) for h in handlers), 'filter missing'\n"
                f"assert {token!r} in redaction.registered(), 'GH_TOKEN not registered'\n"
                f"main.log.warning('leaked %s', {token!r})\n")
        result = _python(code, GH_TOKEN=token)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertNotIn(token, result.stderr)
        self.assertIn("leaked [REDACTED]", result.stderr)

    def test_new_flags_default_to_legacy_behaviour(self):
        result = _python("import sys; sys.path.insert(0, 'src'); import config; "
                         "print(config.EMPTY_SUITE_FAILS)")
        self.assertEqual(result.stdout.strip(), "False", result.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
