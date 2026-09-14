"""Upload evidence videos to Google Drive and hand back a shareable link.

The stitched Playwright mp4 is the one artefact that routinely outgrows the Gmail
attachment cap, and the activity trail (an issue comment or a Doc comment thread)
cannot carry a file at all — so the video goes to Drive and everything else links
to it. Best-effort by design: any failure is logged and reported as "no link" so the
caller can fall back to attaching the file as before.

The Google client libraries are imported lazily: main.py imports this module at
startup and the FSM tests run without googleapiclient installed.
"""
import logging
from pathlib import Path

import config

log = logging.getLogger(__name__)

_SCOPE_HINT = ("uploading to Drive needs the full Drive scope; re-run "
               "scripts/setup_oauth.py on the host to grant it (data/token.json was "
               "issued with the old read-only scope)")

# Resolved once per process: the folder is looked up (or created) on the first upload
# and reused afterwards. Cleared on any upload error so a folder that went away
# (trashed, wrong CODEBOT_DRIVE_FOLDER_ID fixed at runtime) is re-resolved next time.
_folder_cache: str | None = None


def reset_cache() -> None:
    global _folder_cache
    _folder_cache = None


def _drive_service():
    from googleapiclient.discovery import build
    from google_auth import load_credentials
    return build("drive", "v3", credentials=load_credentials(), cache_discovery=False)


def _escape(value: str) -> str:
    """Escape a literal for a Drive `q` string (single-quoted, backslash-escaped)."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _folder_id(service) -> str:
    """The folder that receives evidence: the configured id, else the named folder at
    the root of My Drive, created on first use."""
    global _folder_cache
    if config.DRIVE_FOLDER_ID:
        return config.DRIVE_FOLDER_ID
    if _folder_cache:
        return _folder_cache
    name = config.DRIVE_FOLDER_NAME
    query = (f"name = '{_escape(name)}' and mimeType = 'application/vnd.google-apps.folder' "
             "and 'root' in parents and trashed = false")
    found = service.files().list(q=query, spaces="drive", fields="files(id)",
                                 pageSize=1).execute(num_retries=3).get("files", [])
    if found:
        _folder_cache = found[0]["id"]
        log.info("using existing Drive folder %r (%s)", name, _folder_cache)
    else:
        created = service.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute(num_retries=3)
        _folder_cache = created["id"]
        log.info("created Drive folder %r (%s)", name, _folder_cache)
    return _folder_cache


def upload_evidence(path: Path, name: str) -> str | None:
    """Upload `path` to the evidence folder as `name`, shared read-only with anyone
    holding the link; returns the web link, or None when anything went wrong (the
    caller then attaches the file instead)."""
    global _folder_cache
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        log.warning("evidence upload skipped: %s is missing or empty", path)
        return None
    try:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        service = _drive_service()
        folder = _folder_id(service)
        media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True)
        created = service.files().create(
            body={"name": name, "parents": [folder]}, media_body=media,
            fields="id,webViewLink", supportsAllDrives=True).execute(num_retries=3)
        link = created["webViewLink"]
        try:
            # "Anyone with the link" so reviewers reading the GitHub comment can watch
            # it without a Google account. A Workspace policy may forbid this: the file
            # is still there and the account owner can open it, so keep the link.
            service.permissions().create(
                fileId=created["id"], body={"type": "anyone", "role": "reader"},
                fields="id", supportsAllDrives=True).execute(num_retries=3)
        except Exception:  # noqa: BLE001
            log.exception("uploaded %s but could not share it by link; only the "
                          "account owner can open %s", name, link)
        log.info("uploaded evidence %s (%d bytes) to Drive: %s",
                 name, path.stat().st_size, link)
        return link
    except Exception as err:  # noqa: BLE001
        _folder_cache = None
        status = getattr(getattr(err, "resp", None), "status", None)
        hint = f" — {_SCOPE_HINT}" if status == 403 else ""
        log.exception("could not upload evidence %s to Drive%s", path, hint)
        return None
