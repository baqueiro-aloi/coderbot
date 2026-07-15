"""One-time, host-side OAuth consent flow.

Prereq: create an OAuth client (Desktop app) in Google Cloud Console with the
Gmail, Docs and Drive APIs enabled, download its JSON to data/credentials.json,
then run:  python3 setup_oauth.py
Writes data/token.json (includes refresh token) for the container to use.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

import config


def main() -> None:
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
