"""Shared credential loading for Gmail/Docs clients."""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import config


def load_credentials() -> Credentials:
    if not config.TOKEN_PATH.exists():
        raise SystemExit(f"Missing {config.TOKEN_PATH}. Run setup_oauth.py on the host first.")
    creds = Credentials.from_authorized_user_file(str(config.TOKEN_PATH), config.SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config.TOKEN_PATH.write_text(creds.to_json())
    return creds
