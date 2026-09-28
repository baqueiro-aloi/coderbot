"""Runtime environment variables must remain editable and documented in setup."""
import ast
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.setup_catalog import BY_KEY, REVIEWED_NON_SETTINGS, normalize_value, relevant, validate
from scripts.setup_env import EnvFile
from scripts import setup as guided_setup

ROOT = Path(__file__).resolve().parent.parent


def runtime_names() -> set[str]:
    found = set()
    for filename in (ROOT / "src").glob("*.py"):
        tree = ast.parse(filename.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "environ" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "environ" and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                found.add(node.slice.value)
    for filename in ("scripts/entrypoint.sh", "scripts/healthcheck.sh", "docker-compose.yml",
                     "docker-compose.ec2.yml", "deploy/aws/docker-compose.aws.yml"):
        found.update(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", (ROOT / filename).read_text()))
    return {name for name in found if name.startswith(("CODEBOT_", "CLAUDE_", "OPENCODE_", "GH_", "GIT_"))}


class CatalogAudit(unittest.TestCase):
    def test_every_runtime_knob_is_in_the_setup_catalog(self):
        self.assertEqual(runtime_names() - BY_KEY.keys() - REVIEWED_NON_SETTINGS, set())

    def test_catalog_is_exhaustive_and_documented_in_env_example(self):
        documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M))
        self.assertEqual(BY_KEY.keys() - documented, set())
        self.assertEqual(documented - BY_KEY.keys() - REVIEWED_NON_SETTINGS, set())

    def test_inactive_integration_settings_are_still_available(self):
        self.assertIn("CODEBOT_GH_LABEL_PREFIX", BY_KEY)
        self.assertIn("CODEBOT_SLACK_APP_TOKEN", BY_KEY)
        self.assertFalse(relevant(BY_KEY["CODEBOT_SLACK_APP_TOKEN"],
                                  {"CODEBOT_COMM_CHANNEL": "email"}))
        self.assertTrue(relevant(BY_KEY["CODEBOT_SLACK_APP_TOKEN"],
                                 {"CODEBOT_COMM_CHANNEL": "slack"}))

    def test_pasted_doc_url_and_multiple_trusted_email_addresses(self):
        from scripts.setup_catalog import validate_value
        doc = BY_KEY["CODEBOT_DOC_ID"]
        self.assertIsNone(validate_value(doc, "https://docs.google.com/document/d/Abc123/edit"))
        self.assertEqual(normalize_value(doc, "https://docs.google.com/document/d/Abc123/edit"), "Abc123")
        self.assertIsNone(validate_value(BY_KEY["CODEBOT_USER_EMAIL"],
                                         "one@example.com,two@example.org"))
        self.assertIsNotNone(validate_value(BY_KEY["CODEBOT_USER_EMAIL"],
                                            "one@example.com,not-an-email"))

    def test_validations_are_conditional(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "project"
            repo.mkdir()
            (repo / ".git").mkdir()
            values = {"CODEBOT_REPO_PATH": str(repo), "GH_TOKEN": "token",
                      "CODEBOT_TASK_SOURCE": "jira", "CODEBOT_COMM_CHANNEL": "slack",
                      "CODEBOT_JIRA_URL": "https://site.atlassian.net",
                      "CODEBOT_JIRA_PROJECT_KEY": "APP", "CODEBOT_JIRA_EMAIL": "bot@example.org",
                      "CODEBOT_JIRA_API_TOKEN": "secret", "CODEBOT_SLACK_CHANNEL_ID": "C123",
                      "CODEBOT_SLACK_BOT_TOKEN": "xoxb-key", "CODEBOT_SLACK_APP_TOKEN": "xapp-key",
                      "CLAUDE_CODE_OAUTH_TOKEN": "token"}
            self.assertEqual(validate(values), [])
            del values["CODEBOT_SLACK_APP_TOKEN"]
            self.assertIn("CODEBOT_SLACK_APP_TOKEN", "\n".join(validate(values)))

    def test_google_scopes_follow_selected_source_channel_and_upload(self):
        self.assertEqual(guided_setup._google_scopes({
            "CODEBOT_TASK_SOURCE": "jira", "CODEBOT_COMM_CHANNEL": "slack",
            "CODEBOT_EVIDENCE_UPLOAD": "off"}), [])
        self.assertEqual(len(guided_setup._google_scopes({
            "CODEBOT_TASK_SOURCE": "gdoc", "CODEBOT_COMM_CHANNEL": "slack",
            "CODEBOT_EVIDENCE_UPLOAD": "off"})), 2)
        self.assertEqual(len(guided_setup._google_scopes({
            "CODEBOT_TASK_SOURCE": "jira", "CODEBOT_COMM_CHANNEL": "email",
            "CODEBOT_EVIDENCE_UPLOAD": "on"})), 2)

    def test_live_preflight_checks_jira_statuses_and_slack_app_without_leaking_tokens(self):
        values = {"CODEBOT_TASK_SOURCE": "jira", "CODEBOT_COMM_CHANNEL": "slack",
                  "CODEBOT_JIRA_URL": "https://site.atlassian.net",
                  "CODEBOT_JIRA_EMAIL": "bot@example.org", "CODEBOT_JIRA_API_TOKEN": "secret",
                  "CODEBOT_JIRA_PROJECT_KEY": "APP", "CODEBOT_SLACK_BOT_TOKEN": "xoxb-secret",
                  "CODEBOT_SLACK_APP_TOKEN": "xapp-secret", "CODEBOT_SLACK_CHANNEL_ID": "C123"}
        responses = [{"accountId": "A"}, {"key": "APP"}, {"statuses": []}]
        statuses = [{"statuses": [{"name": n} for n in ("Ready", "In progress", "In review", "Done")]}]
        responses = [responses[0], responses[1], statuses,
                     {"ok": True, "user_id": "U1"},
                     {"ok": True, "channel": {"is_channel": True,
                                              "is_private": False, "is_member": True}},
                     {"ok": True, "url": "wss://slack"}]
        class Result:
            def __init__(self, value):
                self.value = value
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                pass
            def read(self):
                import json
                return json.dumps(self.value).encode()
        with patch.object(guided_setup.urllib.request, "urlopen",
                          side_effect=[Result(value) for value in responses]) as calls:
            self.assertEqual(guided_setup.preflight(values), [])
        self.assertEqual(calls.call_count, 6)
        values["CODEBOT_JIRA_DONE_STATUS"] = "Not a status"
        values["CODEBOT_COMM_CHANNEL"] = "email"
        with patch.object(guided_setup.urllib.request, "urlopen",
                          side_effect=[Result(value) for value in responses[:3]]):
            errors = guided_setup.preflight(values)
        self.assertIn("CODEBOT_JIRA_DONE_STATUS", "\n".join(errors))


class LosslessEnv(unittest.TestCase):
    def test_preserves_unknown_comments_inactive_values_and_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            original = ("# keep this comment\nUNRECOGNIZED=legacy\n"
                        "CODEBOT_SLACK_BOT_TOKEN=secret\nCODEBOT_DOC_ID=inactive-doc\n")
            path.write_text(original)
            env = EnvFile(path)
            self.assertEqual(env.preview({"CODEBOT_SLACK_BOT_TOKEN": "new-secret"}),
                             "CODEBOT_SLACK_BOT_TOKEN: (set) -> (set)")
            with self.assertRaises(ValueError):
                env.save({"CODEBOT_SLACK_CHANNEL_ID": "invalid"})
            self.assertEqual(path.read_text(), original)
            # Save is only possible after all selected required fields are valid.
            with patch("scripts.setup_env.validate", return_value=[]):
                backup = env.save({"CODEBOT_SLACK_CHANNEL_ID": "C123"})
            self.assertEqual(backup.read_text(), original)
            self.assertIn("UNRECOGNIZED=legacy\n", path.read_text())
            self.assertIn("CODEBOT_SLACK_BOT_TOKEN=secret\n", path.read_text())
            self.assertIn("CODEBOT_DOC_ID=inactive-doc\n", path.read_text())
            self.assertIn("CODEBOT_SLACK_CHANNEL_ID=C123\n", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cancel_after_valid_preview_preserves_original_bytes_and_creates_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "project"
            repo.mkdir()
            (repo / ".git").mkdir()
            path = root / ".env"
            original = (f"CODEBOT_REPO_PATH={repo}\nGH_TOKEN=secret\nCODEBOT_DOC_ID=doc\n"
                        "CODEBOT_USER_EMAIL=person@example.org\nCLAUDE_CODE_OAUTH_TOKEN=token\n"
                        "# keep unchanged\n")
            path.write_text(original)
            with patch("builtins.input", return_value="n"), redirect_stdout(StringIO()):
                self.assertFalse(guided_setup._apply(EnvFile(path),
                                                     {"CODEBOT_PROJECT_NAME": "renamed"}))
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(root.glob(".env.bak.*")), [])

    def test_text_mode_can_complete_first_time_setup_without_textual(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "project"
            repo.mkdir()
            (repo / ".git").mkdir()
            answers = [str(repo), "", "", "", "", "", "gh-secret",
                       "", "doc-id", "", "", "user@example.org", "",
                       "claude-secret", "", "", "", "n", "y"]
            output = StringIO()
            with patch.object(guided_setup, "ROOT", root), \
                 patch("builtins.input", side_effect=answers), \
                 patch.object(guided_setup.sys.stdin, "isatty", return_value=False), \
                 redirect_stdout(output):
                self.assertTrue(guided_setup.text_setup(EnvFile(root / ".env")))
            saved = (root / ".env").read_text()
            self.assertIn("CODEBOT_REPO_PATH=", saved)
            self.assertIn("GH_TOKEN=gh-secret", saved)
            self.assertIn("CODEBOT_DOC_ID=doc-id", saved)
            self.assertNotIn("gh-secret", output.getvalue())

    def test_unavailable_tui_falls_back_to_text_without_editing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = "# previous setup\nUNKNOWN_SECRET=leave-me-alone\n"
            (root / ".env").write_text(original)
            with patch.object(guided_setup, "ROOT", root), \
                 patch.object(guided_setup.sys, "argv", ["setup"]), \
                 patch.object(guided_setup.sys.stdin, "isatty", return_value=True), \
                 patch.object(guided_setup.sys.stdout, "isatty", return_value=True), \
                 patch.dict("os.environ", {"TERM": "xterm-256color"}), \
                 patch.object(guided_setup, "_ensure_textual", side_effect=RuntimeError("offline")), \
                 patch.object(guided_setup, "text_setup", return_value=False) as fallback, \
                 redirect_stdout(StringIO()):
                self.assertEqual(guided_setup.main(), 1)
            fallback.assert_called_once()
            self.assertEqual((root / ".env").read_text(), original)

    def test_installed_textual_relaunches_inside_venv_even_if_python_is_symlinked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv_python = root / ".venv/bin/python"
            venv_python.parent.mkdir(parents=True)
            venv_python.symlink_to(guided_setup.sys.executable)
            self.assertEqual(venv_python.resolve(), Path(guided_setup.sys.executable).resolve())
            with patch.object(guided_setup, "ROOT", root), \
                 patch.object(guided_setup.sys, "argv", ["setup"]), \
                 patch.object(guided_setup.sys.stdin, "isatty", return_value=True), \
                 patch.object(guided_setup.sys.stdout, "isatty", return_value=True), \
                 patch.object(guided_setup.sys, "prefix", "/usr/local/system-python"), \
                 patch.dict("os.environ", {"TERM": "xterm-256color"}), \
                 patch.object(guided_setup, "_ensure_textual", return_value=venv_python), \
                 patch.object(guided_setup.subprocess, "call", return_value=0) as relaunch:
                self.assertEqual(guided_setup.main(), 0)
            self.assertEqual(relaunch.call_args.args[0],
                             [str(venv_python), "-m", "scripts.setup"])
            self.assertEqual(relaunch.call_args.kwargs["env"]["CODEBOT_SETUP_TUI_READY"], "1")


if __name__ == "__main__":
    unittest.main()
