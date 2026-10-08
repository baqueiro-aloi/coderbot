"""Controller-owned, restart-safe evidence publication independent of product phases."""
from pathlib import Path

import artifact_manifest
import delivery_checkpoint
import drive_client
import evidence
import config
from execution_identity import digest, snapshot


def publish(store, state, repo, video):
    """Common publication step used by every controller delivery path."""
    if not config.EVIDENCE_UPLOAD:
        return {"status": "blocked", "stage": "upload", "error": "Evidence upload is disabled"}
    if not evidence.valid_media(video):
        return {"status": "retryable", "stage": "conversion", "error": "Video is not playable"}
    identity = digest([state.get("pr_url"), artifact_manifest.file_hash(video), "verified-upload-v2",
                       config.DRIVE_FOLDER_ID])
    task = store.task_identity(state, repo)
    name = f"{state.get('branch', 'evidence')}-{identity[:12]}.mp4"
    uploaded = delivery_checkpoint.step(store, task, identity, "UPLOAD",
        lambda: drive_client.publish_evidence(video, name, upload_only=True),
        validate=lambda r: r.get("status") == "complete" and bool(r.get("id")) and bool(r.get("url")))
    if uploaded.get("status") != "complete":
        return uploaded
    access_identity = digest([identity, uploaded["id"], config.DRIVE_SHARE_MODE, config.DRIVE_REVIEWERS])
    return delivery_checkpoint.step(store, task, access_identity, "ACCESS",
        lambda: drive_client.publish_evidence(video, name, uploaded=uploaded),
        validate=lambda r: r.get("status") == "complete" and r.get("access") and bool(r.get("url")))


def deliver(store, state, repo, *, sync_pr, notify, operations=None):
    operations = operations or ["record", "convert", "upload", "pr_sync", "notify"]
    content = snapshot(repo)
    task = store.task_identity(state, repo)
    identity = digest([state.get("pr_url"), content, state.get("e2e_specs", []), "verified-evidence-v1"])
    paths = delivery_checkpoint.step(store, task, identity, "RECORD",
        lambda: [str(p) for p in evidence.record_evidence(state.get("e2e_specs", []), state.get("e2e_kind"))],
        validate=evidence.valid_paths)
    if not evidence.valid_paths(paths):
        return {"status": "retryable", "stage": "capture/validation", "error": "No valid current evidence recorded"}
    if not any(op in operations for op in ("convert", "upload", "pr_sync")):
        delivery_checkpoint.step(store, task, identity, "NOTIFY_FILES",
            lambda: _notify_files(notify, state, paths), validate=bool)
        return {"status": "complete", "stage": "delivered", "files": paths}
    videos = [Path(p) for p in paths if Path(p).suffix.lower() in (".mp4", ".webm")]
    if not videos:
        return {"status": "not_applicable", "stage": "video", "files": paths}
    def convert():
        result = next((p for p in videos if p.suffix.lower() == ".mp4"), None)
        result = result or evidence.stitch_playwright_clips(videos)
        return str(result) if result else None
    converted = delivery_checkpoint.step(store, task, identity, "CONVERT", convert,
        validate=lambda p: bool(p) and p != "None" and evidence.valid_media(Path(p)))
    if not converted or not evidence.valid_media(Path(converted)):
        return {"status": "retryable", "stage": "conversion", "error": "MP4 conversion or media verification failed"}
    if snapshot(repo) != content:
        return {"status": "retryable", "stage": "provenance", "error": "Implementation changed before publication"}
    video = Path(converted)
    if not any(op in operations for op in ("upload", "pr_sync")):
        delivery_checkpoint.step(store, task, identity, "NOTIFY_MP4",
            lambda: _notify_files(notify, state, [str(video)]), validate=bool)
        return {"status": "complete", "stage": "delivered", "files": [str(video)]}
    published = publish(store, state, repo, video)
    if published.get("status") != "complete":
        return published
    state["evidence_url"] = published["url"]
    upload_identity = digest([identity, artifact_manifest.file_hash(video), published["url"]])
    if "pr_sync" in operations:
        synced = delivery_checkpoint.step(store, task, upload_identity, "PR_SYNC",
            lambda: _sync(sync_pr, state, published["url"]), validate=bool)
        if not synced:
            return {"status": "retryable", "stage": "pr_sync", "url": published["url"]}
    delivery_checkpoint.step(store, task, upload_identity, "NOTIFY",
        lambda: _notify(notify, state, published["url"]), validate=bool)
    return {**published, "stage": "delivered"}


def _sync(sync, state, url):
    sync(state, url)
    return True


def _notify(notify, state, url):
    notify(state, "evidence delivered", f"Video: {url}\nPR: {state['pr_url']}")
    if not state.get("thread_id"):
        raise RuntimeError("Evidence link message delivery returned no task thread")
    return True


def _notify_files(notify, state, paths):
    notify(state, "evidence recorded", "Validated implementation evidence attached.", [Path(p) for p in paths])
    if state.get("last_delivery", {}).get("complete") is False:
        raise RuntimeError("Evidence attachments were not fully delivered")
    return True
