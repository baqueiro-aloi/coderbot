"""Guided configuration entrypoint, with an optional Textual terminal interface."""
import argparse
import base64
import getpass
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.setup_catalog import BY_KEY, SETTINGS, effective, normalize_value, relevant, validate, validate_value
from scripts.setup_env import EnvFile

ROOT = Path(__file__).resolve().parent.parent
PRIMARY_PAGES = ("Repository", "Backlog", "Conversation", "Agent", "Evidence")

# Universal, version-pinned PyPI wheels. Direct wheels avoid slow/broken simple-
# index metadata lookups on hosts with stale private pip index credentials.
_SETUP_WHEELS = (
    "https://files.pythonhosted.org/packages/fb/be/35261223d9416a0751cdff1c7b4a6f881387218a12d439fe22fefebc8c04/textual-8.2.8-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/b3/81/4da04ced5a082363ecfa159c010d200ecbd959ae410c10c0264a38cac0f5/markdown_it_py-4.2.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/a5/69/6da5581c6a7fede7dc261bf4e67d6adca4196f176b43288b55b3db395b6e/mdit_py_plugins-0.6.1-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/40/31/1521c38d175108ac395941adbcb9f11e085340bed81ad166e8ad8c21c17b/platformdirs-4.12.1-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/82/3b/64d4899d73f91ba49a8c18a8ff3f0ea8f1c1d75481760df8c68ef5235bf5/rich-15.0.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/13/d4/1152d1c7ab42d8b908be64fd200ddc870dc9d4925e951198702084aa1a7d/linkify_it_py-2.2.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/61/73/d21edf5b204d1467e06500080a50f79d49ef2b997c79123a536d4a17d97c/uc_micro_py-2.0.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl",
)


def fields_for(page: str, values: dict[str, str], search: str = ""):
    if page == "Repository":
        return [s for s in SETTINGS if s.group == "Repository" and not s.advanced]
    if page == "Backlog":
        return [s for s in SETTINGS if s.key == "CODEBOT_TASK_SOURCE" or
                (s.group in ("GDoc", "GitHub", "Jira") and relevant(s, values) and not s.advanced)]
    if page == "Conversation":
        return [s for s in SETTINGS if s.key == "CODEBOT_COMM_CHANNEL" or
                (s.group in ("Email", "Slack") and relevant(s, values) and not s.advanced)]
    if page == "Agent":
        return [s for s in SETTINGS if s.key == "CODEBOT_AGENT" or
                (s.group in ("Claude", "OpenCode") and relevant(s, values) and not s.advanced)]
    if page == "Evidence":
        return [s for s in SETTINGS if s.group == "Evidence" and not s.advanced]
    if page == "Advanced":
        return [s for s in SETTINGS if search.casefold() in (s.key + " " + s.help).casefold()]
    return []


def _help_for(values: dict[str, str]) -> str:
    source = values.get("CODEBOT_TASK_SOURCE") or "gdoc"
    channel = values.get("CODEBOT_COMM_CHANNEL") or "email"
    agent = values.get("CODEBOT_AGENT") or "claude"
    lines = ["GH_TOKEN is required for GitHub PRs in every combination."]
    if source == "gdoc":
        lines.append("GDoc: create a Google Desktop OAuth client and enable Docs and Drive APIs.")
    elif source == "github":
        lines.append("GitHub Projects: GH_TOKEN also needs project write permission.")
    else:
        lines.append("Jira: https://id.atlassian.com/manage-profile/security/api-tokens")
    if channel == "email":
        lines.append("Email: enable the Gmail API and use scripts/setup_oauth.py for consent.")
    else:
        lines.append("Slack: create a separate app per bot, install it in the public channel, "
                     "enable Socket Mode (connections:write) and subscribe to message.channels "
                     "with channels:history, channels:read, chat:write and files:write bot scopes.")
    if (values.get("CODEBOT_EVIDENCE_UPLOAD") or "on").lower() not in ("off", "false", "0", "no"):
        lines.append("Drive evidence upload is on: enable Drive API and complete Google OAuth consent.")
    if agent == "opencode":
        lines.append("After saving: run OpenCode provider login in the container (Docker Compose).")
    else:
        lines.append("Claude: run `claude setup-token` on the host and enter its result.")
    return "\n".join(lines)


def _post_save_auth(values: dict[str, str]):
    google_needed = ((values.get("CODEBOT_TASK_SOURCE") or "gdoc") == "gdoc" or
                     (values.get("CODEBOT_COMM_CHANNEL") or "email") == "email" or
                     (values.get("CODEBOT_EVIDENCE_UPLOAD") or "on").lower()
                     not in ("off", "false", "0", "no"))
    if google_needed:
        token = ROOT / "data/token.json"
        credentials = ROOT / "data/credentials.json"
        scopes = _google_scopes(values)
        google_apis = (["gmail"] if any("gmail" in scope for scope in scopes) else []) + \
                      (["docs"] if any("documents" in scope for scope in scopes) else []) + \
                      (["drive"] if any("drive" in scope for scope in scopes) else [])
        print("Google APIs to enable: " + ", ".join(google_apis))
        for api in google_apis:
            print(f"  https://console.cloud.google.com/apis/library/{api}.googleapis.com")
        if token.exists():
            try:
                granted = set(json.loads(token.read_text()).get("scopes") or [])
            except (OSError, ValueError):
                granted = set()
            needed = set(_google_scopes(values))
            if not needed.issubset(granted):
                print("Google token lacks scopes for the selected modes; run "
                      "`python3 scripts/setup_oauth.py` to re-consent.")
            else:
                print(f"Google token already present at {token} with the required scopes.")
        elif credentials.exists():
            print("Google credentials found; run `python3 scripts/setup_oauth.py` to authorize required scopes.")
        else:
            print(f"Google OAuth client needed: save Desktop app credentials to {credentials}, "
                  "then run `python3 scripts/setup_oauth.py`.")
            print("  Create the Desktop OAuth client: https://console.cloud.google.com/apis/credentials")
        if credentials.exists() and sys.stdin.isatty() and _confirm("Run Google consent flow now?"):
            try:
                python = ROOT / ".venv/bin/python"
                if not python.exists():
                    subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")],
                                   check=True, timeout=60)
                subprocess.run([str(python), "-m", "pip", "install", "-r",
                                str(ROOT / "requirements.txt"), "--index-url", "https://pypi.org/simple",
                                "--timeout", "10", "--retries", "1"],
                               check=True, timeout=120)
                subprocess.run([str(python), "scripts/setup_oauth.py"], cwd=ROOT, check=True)
            except (OSError, subprocess.SubprocessError) as error:
                print(f"Google consent did not complete: {error}. "
                      "Run `python3 scripts/setup_oauth.py` after installing requirements.txt.")
    if (values.get("CODEBOT_AGENT") or "claude") == "opencode":
        provider = values.get("OPENCODE_PROVIDER", "")
        docker_auth = ["docker", "compose", "run", "--rm", "--no-deps",
                       "--entrypoint", "opencode", "-e", "XDG_DATA_HOME=/app/data/opencode/data",
                       "-e", "XDG_CONFIG_HOME=/app/data/opencode/config", "-e",
                       "XDG_CACHE_HOME=/app/data/opencode/cache", "-e",
                       "XDG_STATE_HOME=/app/data/opencode/state", "codebot", "auth", "login",
                       "--provider", provider]
        print(f"OpenCode provider {provider}: authenticate inside the container using "
              "the guided browser/device-code/API-key flow.")
        if sys.stdin.isatty() and shutil.which("docker") and _confirm("Build the image and log in now?"):
            try:
                subprocess.run(["docker", "compose", "build", "codebot"], cwd=ROOT, check=True)
                subprocess.run(docker_auth, cwd=ROOT, check=True)
            except (OSError, subprocess.SubprocessError) as error:
                print(f"OpenCode login did not complete: {error}; retry the provider login later.")
        else:
            print("When ready, build with `docker compose build codebot` and authenticate "
                  "the selected OpenCode provider in data/opencode/ via the container.")


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt + " [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _google_scopes(values: dict[str, str]) -> list[str]:
    scopes = []
    if (values.get("CODEBOT_COMM_CHANNEL") or "email") == "email":
        scopes.append("https://www.googleapis.com/auth/gmail.modify")
    if (values.get("CODEBOT_TASK_SOURCE") or "gdoc") == "gdoc":
        scopes.append("https://www.googleapis.com/auth/documents")
    if ((values.get("CODEBOT_TASK_SOURCE") or "gdoc") == "gdoc" or
            (values.get("CODEBOT_EVIDENCE_UPLOAD") or "on").lower() not in ("off", "false", "0", "no")):
        scopes.append("https://www.googleapis.com/auth/drive")
    return scopes


def preflight(values: dict[str, str]) -> list[str]:
    """Check selected Jira/Slack credentials before replacing a working .env."""
    errors = []

    def get(url: str, authorization: str, *, method="GET"):
        req = urllib.request.Request(url, method=method,
                                     headers={"Authorization": authorization, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code}") from error
        except (OSError, ValueError) as error:
            raise RuntimeError(f"connection failed: {error}") from error

    if (values.get("CODEBOT_TASK_SOURCE") or "gdoc") == "jira":
        site = values["CODEBOT_JIRA_URL"].rstrip("/")
        key = urllib.parse.quote(values["CODEBOT_JIRA_PROJECT_KEY"], safe="")
        token = base64.b64encode((values["CODEBOT_JIRA_EMAIL"] + ":" +
                                  values["CODEBOT_JIRA_API_TOKEN"]).encode()).decode()
        try:
            get(f"{site}/rest/api/3/myself", "Basic " + token)
            get(f"{site}/rest/api/3/project/{key}", "Basic " + token)
            statuses = get(f"{site}/rest/api/3/project/{key}/statuses", "Basic " + token)
            available = {entry["name"].casefold() for issue_type in statuses
                         for entry in issue_type.get("statuses", [])}
            for setting in ("CODEBOT_JIRA_PICK_STATUS", "CODEBOT_JIRA_ACTIVE_STATUS",
                            "CODEBOT_JIRA_REVIEW_STATUS", "CODEBOT_JIRA_DONE_STATUS"):
                if (values.get(setting) or BY_KEY[setting].default).casefold() not in available:
                    errors.append(f"{setting}: unavailable in project {values['CODEBOT_JIRA_PROJECT_KEY']}")
        except RuntimeError as error:
            errors.append(f"Jira credentials/project: {error}")

    if (values.get("CODEBOT_COMM_CHANNEL") or "email") == "slack":
        token = "Bearer " + values["CODEBOT_SLACK_BOT_TOKEN"]
        try:
            auth = get("https://slack.com/api/auth.test", token, method="POST")
            if not auth.get("ok"):
                raise RuntimeError(f"bot token: {auth.get('error', 'invalid')}")
            channel_id = urllib.parse.quote(values["CODEBOT_SLACK_CHANNEL_ID"], safe="")
            info = get(f"https://slack.com/api/conversations.info?channel={channel_id}", token)
            if not info.get("ok") or not info.get("channel", {}).get("is_channel") or \
                    info["channel"].get("is_private") or not info["channel"].get("is_member"):
                raise RuntimeError("bot must join the selected public channel with channels:history")
            connection = get("https://slack.com/api/apps.connections.open",
                             "Bearer " + values["CODEBOT_SLACK_APP_TOKEN"], method="POST")
            if not connection.get("ok"):
                raise RuntimeError(f"Socket Mode app token: {connection.get('error', 'invalid')}")
        except RuntimeError as error:
            errors.append(f"Slack channel/app: {error}")
    return errors


def _apply(env: EnvFile, changes: dict[str, str]) -> bool:
    errors = validate(env.with_changes(changes))
    if errors:
        print("Fix these settings before saving:\n- " + "\n- ".join(errors))
        return False
    if errors := preflight(env.with_changes(changes)):
        print("Check integration access before saving:\n- " + "\n- ".join(errors))
        return False
    print("\nReview changes (secrets masked):\n" + env.preview(changes))
    if input("Save configuration? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Canceled; .env was not changed.")
        return False
    backup = env.save(changes)
    print(f"Saved {env.path}" + (f" (backup: {backup})" if backup else ""))
    _post_save_auth(env.with_changes(changes))
    return True


def text_setup(env: EnvFile) -> bool:
    """Complete text-mode fallback; no third-party TUI dependency is needed."""
    changes = {}
    values = dict(env.values)
    for page in PRIMARY_PAGES:
        print(f"\n━━ {page} ━━")
        queue = list(fields_for(page, values))
        index = 0
        while index < len(queue):
            setting = queue[index]
            current = effective(setting, values)
            shown = "(set; hidden)" if setting.secret and current else current or "(empty)"
            choices = " / ".join(setting.choices)
            print(setting.help + (f" Options: {choices}" if choices else ""))
            prompt = f"{setting.key} [{shown}] (Enter keeps; /clear empties): "
            try:
                entered = (getpass.getpass(prompt) if setting.secret and sys.stdin.isatty()
                           else input(prompt)).strip()
            except EOFError:
                print("Setup canceled; no configuration written.")
                return False
            value = "" if entered == "/clear" else current if not entered else entered
            if error := validate_value(setting, value):
                print(f"  {error}")
                continue
            if entered:
                value = normalize_value(setting, value)
                values[setting.key] = value
                changes[setting.key] = value
            if setting.key in ("CODEBOT_TASK_SOURCE", "CODEBOT_COMM_CHANNEL", "CODEBOT_AGENT"):
                queue = list(fields_for(page, values))
            index += 1
    print("\n" + _help_for(values))
    if input("Review advanced settings? [y/N] ").strip().lower() in ("y", "yes"):
        while True:
            search = input("Search settings (blank to finish): ").strip()
            if not search:
                break
            matching = fields_for("Advanced", values, search)
            for setting in matching:
                print(f"  {setting.key}: {setting.help}")
            key = input("Enter a key to edit (blank to search again): ").strip().upper()
            if key not in BY_KEY:
                continue
            setting = BY_KEY[key]
            shown = "(set; hidden)" if setting.secret and effective(setting, values) else effective(setting, values) or "(empty)"
            entered = (getpass.getpass(f"{key} [{shown}]: ") if setting.secret and sys.stdin.isatty()
                       else input(f"{key} [{shown}]: ")).strip()
            if not entered:
                continue
            value = "" if entered == "/clear" else entered
            if error := validate_value(setting, value):
                print(error)
                continue
            value = normalize_value(setting, value)
            values[key] = value
            changes[key] = value
    return _apply(env, changes)


def _ensure_textual():
    host_venv = ROOT / ".venv"
    python = host_venv / "bin/python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(host_venv)], check=True, timeout=60)
    elif subprocess.run([str(python), "-c", "import textual"], capture_output=True,
                        timeout=10).returncode == 0:
        return python
    # All wheels are universal Python packages; fall back to pinned requirements
    # through the public index if any direct URL becomes unavailable.
    try:
        install = subprocess.run([str(python), "-m", "pip", "install", "--no-index",
                                  "--timeout", "10", "--retries", "1", *_SETUP_WHEELS],
                                 timeout=100, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        install = None
    if install is None or install.returncode:
        install = subprocess.run([str(python), "-m", "pip", "install", "-r",
                                  str(ROOT / "scripts/requirements-setup.txt"),
                                  "--index-url", "https://pypi.org/simple", "--timeout", "10",
                                  "--retries", "1"], timeout=100, capture_output=True, text=True,
                                 env=os.environ | {"PIP_CONFIG_FILE": os.devnull})
    if install.returncode:
        raise RuntimeError("Could not install Textual; check PyPI access or use --text")
    return python


def main():
    parser = argparse.ArgumentParser(description="Configure Coderbot (Jira, Slack, Google and GitHub)")
    parser.add_argument("--text", action="store_true", help="use the line-oriented fallback")
    args = parser.parse_args()
    env = EnvFile(ROOT / ".env")
    if not args.text and sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM") not in ("dumb", ""):
        try:
            python = _ensure_textual()
            # Venv's bin/python is commonly a symlink to the system binary.
            # Comparing resolved executable paths mistakes the system interpreter
            # for the venv and then `import textual` fails despite a successful
            # install into .venv. sys.prefix identifies the active environment.
            if Path(sys.prefix).absolute() != (ROOT / ".venv").absolute():
                return subprocess.call([str(python), "-m", "scripts.setup"], cwd=ROOT,
                                       env=os.environ | {"CODEBOT_SETUP_TUI_READY": "1"})
            from scripts.setup_ui import run
            return 0 if run(env) else 1
        except (OSError, subprocess.SubprocessError, RuntimeError, ImportError) as error:
            print(f"Terminal UI unavailable ({error}); continuing in text mode.")
    if os.environ.get("CODEBOT_SETUP_TUI_READY") and not args.text:
        from scripts.setup_ui import run
        return 0 if run(env) else 1
    return 0 if text_setup(env) else 1


if __name__ == "__main__":
    raise SystemExit(main())
