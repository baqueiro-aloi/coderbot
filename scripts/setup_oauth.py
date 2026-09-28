"""One-time, host-side OAuth consent flow.

Prereq: create an OAuth client (Desktop app) in Google Cloud Console with the
Gmail, Docs and Drive APIs enabled, download its JSON to data/credentials.json,
then run (from the repo root):  python3 scripts/setup_oauth.py
Writes data/token.json (includes refresh token) for the container to use.
"""
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.setup_env import EnvFile  # noqa: E402

# Host-side consent uses the selected modes from .env, not config.py's defaults.
for key, value in EnvFile(ROOT / ".env").values.items():
    os.environ.setdefault(key, value)
import config  # noqa: E402


def main() -> None:
    if not config.SCOPES:
        raise SystemExit("Google OAuth is not needed for the selected backlog, conversation "
                         "and evidence settings")
    if not config.CREDENTIALS_PATH.exists():
        raise SystemExit(
            f"Missing {config.CREDENTIALS_PATH}. Download the OAuth client JSON "
            "(Desktop app) from Google Cloud Console first."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(config.CREDENTIALS_PATH), config.SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    config.TOKEN_PATH.write_text(creds.to_json())
    print(f"Token saved to {config.TOKEN_PATH}")


if __name__ == "__main__":
    main()
