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
import hashlib
from pathlib import Path

import config

log = logging.getLogger(__name__)

_SCOPE_HINT = ("uploading to Drive needs the full Drive scope; re-run "
               "scripts/setup_oauth.py on the host to grant it (data/token.json was "
                "issued with the old read-only scope)")


def _collection(payload, name):
    values = payload.get(name) if isinstance(payload, dict) else None
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise ValueError('Drive response missing or malformed ' + name)
    return values


def _id(payload, name='id'):
    value = payload.get(name) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError('Drive response missing ' + name)
    return value

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
    found = _collection(service.files().list(q=query, spaces="drive", fields="files(id)",
                                 pageSize=1).execute(num_retries=3), 'files')
    if found:
        _folder_cache = _id(found[0])
        log.info("using existing Drive folder %r (%s)", name, _folder_cache)
    else:
        created = service.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute(num_retries=3)
        _folder_cache = _id(created)
        log.info("created Drive folder %r (%s)", name, _folder_cache)
    return _folder_cache


def publish_evidence(path: Path, name: str, *, upload_only=False, uploaded=None) -> dict:
    """Upload once by hash, then independently establish authorized reviewer access.

    Failed access preserves the remote ID and URL without declaring delivery complete.
    """
    global _folder_cache
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        log.warning("evidence upload skipped: %s is missing or empty", path)
        return {"status": "retryable", "stage": "upload", "error": "missing or empty video"}
    try:
        from googleapiclient.http import MediaFileUpload
        service = _drive_service()
        folder = _folder_id(service)
        identity = hashlib.sha256(path.read_bytes()).hexdigest()
        existing = [{"id": _id(uploaded), "webViewLink": uploaded.get("url") or uploaded.get("webViewLink")}] if uploaded else _collection(service.files().list(
            q=f"'{_escape(folder)}' in parents and trashed = false and appProperties has {{ key='codebotEvidence' and value='{identity}' }}",
            fields="files(id,webViewLink)", pageSize=1, supportsAllDrives=True,
            includeItemsFromAllDrives=True).execute(num_retries=3), 'files')
        if existing:
            created = existing[0]
        else:
            media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True)
            created = service.files().create(
                body={"name": name, "parents": [folder], "appProperties": {"codebotEvidence": identity}}, media_body=media,
                fields="id,webViewLink", supportsAllDrives=True).execute(num_retries=3)
        link = _id(created, 'webViewLink')
        result = {"status": "blocked", "stage": "access", "id": _id(created), "url": link,
                  "hash": identity, "access": False}
        if upload_only:
            return {**result, "status": "complete", "stage": "upload"}
        try:
            permissions = _collection(service.permissions().list(fileId=_id(created),
                fields="permissions(type,role,emailAddress,domain)", supportsAllDrives=True).execute(num_retries=3), 'permissions')
            result.update(verify_inherited(service, _id(created), folder, permissions))
        except Exception:  # noqa: BLE001
            log.exception("uploaded %s but could not verify inherited access for %s", name, link)
            result.update(status="retryable", error="Inherited permission verification failed")
        log.info("uploaded evidence %s (%d bytes) to Drive: %s",
                 name, path.stat().st_size, link)
        return result
    except Exception as err:  # noqa: BLE001
        _folder_cache = None
        status = getattr(getattr(err, "resp", None), "status", None)
        hint = f" — {_SCOPE_HINT}" if status == 403 else ""
        log.exception("could not upload evidence %s to Drive%s", path, hint)
        return {"status": "retryable", "stage": "upload", "error": str(err)}


def upload_evidence(path: Path, name: str) -> str | None:
    """Compatibility wrapper: only return links with verified reviewer access."""
    result = publish_evidence(path, name)
    return result.get("url") if result.get("access") else None


def verify_inherited(service, file_id, folder, permissions=None):
    """Verify parent and effective folder ACL without mutating any permissions."""
    file = service.files().get(fileId=file_id, fields="id,parents,trashed", supportsAllDrives=True).execute(num_retries=3)
    if file.get("trashed") or folder not in file.get("parents", []):
        return {"status": "blocked", "access": False, "error": "Evidence is not in the authorized folder"}
    if permissions is None:
        permissions = _collection(service.permissions().list(fileId=file_id, fields="permissions(type,role,emailAddress,domain)", supportsAllDrives=True).execute(num_retries=3), 'permissions')
    parent = _collection(service.permissions().list(fileId=folder, fields="permissions(type,role,emailAddress,domain)", supportsAllDrives=True).execute(num_retries=3), 'permissions')
    def identities(entries):
        return {(p.get("type"), p.get("emailAddress", "").lower(), p.get("domain", "").lower()) for p in entries
                if p.get("role") in ("reader", "writer", "owner", "organizer", "fileOrganizer")}
    inherited = identities(parent)
    if not inherited or not inherited.issubset(identities(permissions)):
        return {"status": "blocked", "access": False, "error": "Folder permissions could not be verified on evidence"}
    return {"status": "complete", "access": True, "access_mode": "inherited", "folder_id": folder}


def verify_existing(file_id, path, folder=None):
    """Read-only remote validation for adoption of an already published MP4."""
    service = _drive_service()
    authorized_folder = _folder_id(service)
    if folder and folder != authorized_folder:
        raise ValueError("Receipt folder is not the configured evidence destination")
    folder = authorized_folder
    file = service.files().get(fileId=file_id, fields="id,webViewLink,parents,size,md5Checksum,mimeType,trashed", supportsAllDrives=True).execute(num_retries=3)
    if file.get("trashed") or file.get("mimeType") != "video/mp4" or int(file.get("size", 0)) != Path(path).stat().st_size or file.get("md5Checksum") != hashlib.md5(Path(path).read_bytes()).hexdigest():
        raise ValueError("Remote evidence differs from verified local MP4")
    access = verify_inherited(service, file_id, folder)
    return {**access, "id": file_id, "url": file["webViewLink"], "hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "stage": "access"}
