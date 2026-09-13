"""Read pending improvements from the Google Doc and strike items through when done.

Multi-instance coordination: picking an instance appends a "[implementing: <name>]"
claim marker to the task's bullet line so other instances skip it. Every doc write
carries the read's revisionId (writeControl.requiredRevisionId), so a doc that changed
under us — another instance claiming, the user typing — fails the write instead of
landing on shifted indexes; the caller re-reads and retries."""
import logging
import re

from google.auth.transport.requests import AuthorizedSession
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from google_auth import load_credentials
from task_text import PRIORITY_RE, normalize, priority_of  # noqa: F401 — re-exported

log = logging.getLogger(__name__)

# Inline doc images are downloaded here so the working Claude session can Read them.
IMAGES_DIR = config.DATA_DIR / "doc_images"

# Per nesting level, when rendering a task's sub-bullets. Levels are used as the doc
# reports them (it skips levels — a top-level bullet may have level-2 children), so the
# shape the user sees in the doc is what the agent sees.
INDENT = "    "


def _docs_service():
    return build("docs", "v1", credentials=load_credentials(), cache_discovery=False)


def _drive_service():
    # Comments on a Doc are a Drive API feature (the Docs API has none).
    return build("drive", "v3", credentials=load_credentials(), cache_discovery=False)


# Claim marker an instance appends to a task's bullet line when it picks the task.
CLAIM_RE = re.compile(r"\s*\[implementing:\s*([^\]]*?)\s*\]", re.IGNORECASE)
# Hold marker: the task was paused by the user (HOLD command) and waits for CONTINUE.
# Held tasks are not pickable by any instance; the holding instance resumes it.
HOLD_RE = re.compile(r"\s*\[on hold:\s*([^\]]*?)\s*\]", re.IGNORECASE)
_MARKER_RE = re.compile(r"\s*\[(?:implementing|on hold):\s*[^\]]*?\s*\]", re.IGNORECASE)


def held_by(text: str) -> str | None:
    """The instance named in the text's hold marker, or None when not on hold."""
    m = HOLD_RE.search(text)
    return (m.group(1).lower() or "?") if m else None
def strip_claims(text: str) -> str:
    """The task text with any [implementing: ...] / [on hold: ...] markers removed."""
    return _MARKER_RE.sub("", text)


def claimed_by(text: str) -> str | None:
    """The instance named in the text's first claim marker, or None when there is no
    marker at all. A malformed/empty marker ("[implementing: ]") returns "?" — still
    CLAIMED, by nobody recognizable — so a half-deleted marker can never make two
    instances both see the task as free and both claim it ("?" can't equal any real
    INSTANCE_ID, which is sanitized to [a-z0-9-])."""
    m = CLAIM_RE.search(text)
    if not m:
        return None
    return m.group(1).lower() or "?"


def _same_item(task_text: str, item_text: str) -> bool:
    """Task identity match, ignoring claim markers on either side (a claimed task must
    still match the clean text codebot stored when it picked the item)."""
    return normalize(strip_claims(task_text)) == normalize(strip_claims(item_text))


def _iter_paragraphs(document: dict):
    """Yield a record per non-empty paragraph, in document order:
    {text, start, end, struck, level, heading, images}. `level` is the list nesting level
    (0 = top-level bullet) or None when the paragraph is not a list item; `heading` marks
    a HEADING_* paragraph, which is how the doc titles its sections. `images` holds the
    inline object ids of images embedded in the paragraph; a paragraph that is ONLY an
    image (no text) is still yielded so the image reaches the task above it.
    """
    for element in document.get("body", {}).get("content", []):
        para = element.get("paragraph")
        if not para:
            continue
        text_parts = []
        runs = []
        images = []
        for pe in para.get("elements", []):
            obj_id = pe.get("inlineObjectElement", {}).get("inlineObjectId")
            if obj_id:
                images.append(obj_id)
            run = pe.get("textRun")
            if not run:
                continue
            content = run.get("content", "")
            if content.strip():
                runs.append(run)
            text_parts.append(content)
        text = "".join(text_parts).strip()
        if not (text and runs) and not images:
            continue
        if "startIndex" not in element or "endIndex" not in element:
            continue
        bullet = para.get("bullet")
        yield {
            "text": text,
            "start": element["startIndex"],
            "end": element["endIndex"],
            "struck": bool(runs) and all(
                run.get("textStyle", {}).get("strikethrough") for run in runs),
            "level": bullet.get("nestingLevel", 0) if bullet else None,
            "heading": bullet is None and para.get("paragraphStyle", {}).get(
                "namedStyleType", "").startswith("HEADING_"),
            "images": images,
        }


def _tasks(document: dict) -> list[dict]:
    """One record per task: {text, detail, struck, section, ranges, images}.

    A task is a top-level bullet; it owns every following sub-bullet until the next
    top-level bullet or section heading, whatever nesting level those sub-bullets carry
    (the doc skips levels, so "deeper than 0" — not "exactly one deeper" — is the rule).
    `detail` renders them as an indented block ("" when the task has none) and `ranges`
    covers the whole group, so striking a task through strikes its sub-bullets too.

    Paragraphs that are neither bullets nor headings (e.g. a note under a heading)
    are not tasks and are ignored — except for their inline images,
    which (like a sub-bullet's images) belong to the task above them: pasted screenshots
    land in the doc as their own non-bullet paragraph under the bullet they illustrate.
    """
    section = ""
    tasks = []
    for para in _iter_paragraphs(document):
        if para["heading"]:
            section = para["text"]
        elif para["level"] == 0 and para["text"]:
            tasks.append({"text": para["text"], "lines": [], "struck": para["struck"],
                          "section": section, "ranges": [(para["start"], para["end"])],
                          "images": list(para["images"])})
        elif tasks and tasks[-1]["section"] == section:
            if para["text"] and para["level"] is not None:
                tasks[-1]["lines"].append(f"{INDENT * para['level']}- {para['text']}")
                tasks[-1]["ranges"].append((para["start"], para["end"]))
            tasks[-1]["images"].extend(para["images"])
        elif para["text"] and para["level"] is not None:
            log.warning("sub-bullet with no task above it; ignoring: %r", para["text"][:80])
    for task in tasks:
        task["detail"] = "\n".join(task.pop("lines"))
    return tasks


def _in_section(task: dict) -> bool:
    """Whether the task sits under the configured heading. An empty DOC_SECTION means
    the whole doc is the backlog (every section is pickable)."""
    return not config.DOC_SECTION or normalize(task["section"]) == normalize(config.DOC_SECTION)


def _pending(tasks: list[dict]) -> list[dict]:
    """The pickable tasks under config.DOC_SECTION (or anywhere, when it is unset): not
    struck through and not claimed by another instance. Text is returned with any claim
    marker stripped. A task claimed by THIS instance stays pickable (flagged
    claimed_by_me) so a claim that outlived a lost state.json is resumed instead of
    orphaned."""
    items = []
    for t in tasks:
        if not _in_section(t) or t["struck"]:
            continue
        owner = claimed_by(t["text"])
        if owner and owner != config.INSTANCE_ID:
            continue  # another instance is implementing it
        if held_by(t["text"]):
            continue  # paused by the user; resumed only through CONTINUE
        items.append({"id": "", "url": "",
                      "text": strip_claims(t["text"]).strip(), "detail": t["detail"],
                      "images": t["images"], "claimed_by_me": owner is not None,
                      "priority": priority_of(t["text"])})
    return items


def _download_images(document: dict, object_ids: list[str]) -> list[str]:
    """Download the doc's inline images to IMAGES_DIR and return the local paths.

    contentUri is short-lived and requires the account's credentials, so images are
    fetched now, while the doc payload is fresh. Best-effort: a failed download is
    logged and skipped — the task still runs, just without that screenshot.
    """
    inline = document.get("inlineObjects", {})
    session = None
    paths = []
    for oid in object_ids:
        uri = (inline.get(oid, {}).get("inlineObjectProperties", {})
               .get("embeddedObject", {}).get("imageProperties", {}).get("contentUri"))
        if not uri:
            log.warning("inline object %s has no contentUri; skipping", oid)
            continue
        dest = IMAGES_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", oid) + ".png")
        try:
            if session is None:
                IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                session = AuthorizedSession(load_credentials())
            resp = session.get(uri, timeout=60)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            paths.append(str(dest))
            log.debug("downloaded doc image %s -> %s (%d bytes)", oid, dest, len(resp.content))
        except Exception:  # noqa: BLE001 — a lost screenshot must not block the backlog
            log.exception("could not download doc image %s", oid)
    if object_ids:
        log.info("downloaded %d/%d inline image(s) for a backlog item", len(paths), len(object_ids))
    return paths


def list_pending_items() -> list[dict]:
    """Pickable backlog tasks in doc order: [{"text": ..., "detail": ..., "images": ...}].

    "detail" holds the task's sub-bullets (the user's clarifications) as an indented
    block, "" when it has none. "images" holds local paths of the item's inline
    screenshots, downloaded from the doc ([] when it has none).
    """
    doc = _docs_service().documents().get(documentId=config.DOC_ID).execute()
    tasks = _tasks(doc)
    items = _pending(tasks)
    for item in items:
        item["images"] = _download_images(doc, item["images"])
    foreign = [claimed_by(t["text"]) for t in tasks
               if _in_section(t) and not t["struck"]
               and claimed_by(t["text"]) not in (None, config.INSTANCE_ID)]
    if foreign:
        log.info("%d backlog item(s) claimed by other instance(s) %s; not pickable",
                 len(foreign), sorted(set(foreign)))
    sections = {t["section"] for t in tasks}
    if config.DOC_SECTION and normalize(config.DOC_SECTION) not in {normalize(s) for s in sections}:
        # Misspelled/renamed heading: every task would be filtered out and codebot would
        # sit idle on a full backlog. Say so rather than reporting an empty backlog.
        log.warning("doc %s has no %r heading; found %s — no items are pickable",
                    config.DOC_ID, config.DOC_SECTION, sorted(sections) or "no headings")
    log.debug("doc %s: %d pending item(s) under %r, of %d task(s) in %d section(s); "
              "%d item(s) carry screenshots",
              config.DOC_ID, len(items), config.DOC_SECTION, len(tasks), len(sections),
              sum(1 for i in items if i["images"]))
    return items


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-be")) // 2


def _marker_ranges(document: dict, task: dict, instance: str | None = None,
                   pattern: re.Pattern = CLAIM_RE) -> list[tuple[int, int]]:
    """Doc index ranges of the task's claim markers (all instances, or just one).

    Docs indexes are UTF-16 code units, so offsets inside a run are accumulated in
    UTF-16 lengths — a straight Python character count drifts past any non-BMP char
    (e.g. an emoji the user pasted before the marker)."""
    spans = set(task["ranges"])
    ranges = []
    for element in document.get("body", {}).get("content", []):
        if (element.get("startIndex"), element.get("endIndex")) not in spans:
            continue
        para = element.get("paragraph")
        if not para:
            continue
        chars: list[tuple[str, int]] = []  # (char, its doc index)
        for pe in para.get("elements", []):
            run = pe.get("textRun")
            if not run:
                continue
            idx = pe.get("startIndex")
            for ch in run.get("content", ""):
                chars.append((ch, idx))
                idx += _utf16_len(ch)
        joined = "".join(ch for ch, _i in chars)
        for m in pattern.finditer(joined):
            if instance is not None and m.group(1).lower() != instance:
                continue
            last_ch, last_idx = chars[m.end() - 1]
            ranges.append((chars[m.start()][1], last_idx + _utf16_len(last_ch)))
    return ranges


def _cas_update(service, doc: dict, requests: list[dict]) -> bool:
    """Apply requests only if the doc is still at the revision we read (compare-and-
    swap). False when the doc changed under us — the caller re-reads and retries."""
    try:
        service.documents().batchUpdate(
            documentId=config.DOC_ID,
            body={"requests": requests,
                  "writeControl": {"requiredRevisionId": doc["revisionId"]}},
        ).execute()
    except HttpError as err:
        if err.resp.status == 400:
            log.info("doc changed since it was read; write rejected, will re-read")
            return False
        raise
    return True


def _find_task(doc: dict, item_text: str) -> dict | None:
    """The doc task matching item_text. The doc can hold duplicate-text bullets (a
    completed struck copy plus a re-added fresh one, or a copy in another section), so
    a bare first-match would let claim_task hit the struck copy (livelocking the pick)
    or mark_done strike a copy that was never worked. Prefer, in order: the copy THIS
    instance claimed, an unclaimed unstruck copy, a foreign-claimed unstruck copy,
    then a struck copy; document order breaks ties."""
    def rank(task: dict) -> int:
        if task["struck"]:
            return 3
        owner = claimed_by(task["text"]) or held_by(task["text"])
        if owner == config.INSTANCE_ID:
            return 0
        return 1 if owner is None else 2

    matches = [t for t in _tasks(doc) if _same_item(t["text"], item_text)]
    return min(matches, key=rank) if matches else None


def _find_mine(doc: dict) -> dict | None:
    """The single unstruck task carrying this instance's claim marker, or None.

    Fallback identity for mark_done/unclaim_task when the stored item text no longer
    matches any bullet — i.e. the user edited the bullet's wording mid-task. The
    marker was written by claim_task at pick time and an instance holds at most one
    claim, so a unique marker-bearing bullet IS the task; without this fallback the
    stale claim survives and do_pick's resume filter re-picks the finished task."""
    mine = [t for t in _tasks(doc)
            if not t["struck"] and claimed_by(t["text"]) == config.INSTANCE_ID]
    if len(mine) > 1:
        log.warning("%d unstruck tasks carry this instance's claim marker; refusing "
                    "to guess which is the current task", len(mine))
        return None
    return mine[0] if mine else None


CAS_ATTEMPTS = 3


def claim_task(item_text: str, item_id: str | None = None) -> bool:
    """Atomically append this instance's claim marker to the task's bullet line so no
    other instance picks it. False when another instance holds the claim (or the task
    vanished/completed) — the caller should pick something else."""
    marker = f" [implementing: {config.INSTANCE_ID}]"
    service = _docs_service()
    for _attempt in range(CAS_ATTEMPTS):
        doc = service.documents().get(documentId=config.DOC_ID).execute()
        task = _find_task(doc, item_text)
        if task is None or task["struck"]:
            log.warning("no unstruck doc task to claim for: %r", item_text[:80])
            return False
        owner = claimed_by(task["text"])
        if owner == config.INSTANCE_ID:
            log.info("task already claimed by this instance: %r", item_text[:80])
            return True
        if owner:
            log.info("task already claimed by %r: %r", owner, item_text[:80])
            return False
        # Insert just before the bullet line's trailing newline.
        insert = {"insertText": {"location": {"index": task["ranges"][0][1] - 1},
                                 "text": marker}}
        if _cas_update(service, doc, [insert]):
            log.info("claimed backlog task for %s: %r", config.INSTANCE_ID, item_text[:80])
            return True
    log.warning("could not claim after %d attempts (doc busy): %r",
                CAS_ATTEMPTS, item_text[:80])
    return False


def unclaim_task(item_text: str, item_id: str | None = None) -> bool:
    """Remove this instance's claim marker so the task returns to the pickable pool
    (used when a task is aborted without completing). False when the task (or a
    settled write) could not be found."""
    service = _docs_service()
    for _attempt in range(CAS_ATTEMPTS):
        doc = service.documents().get(documentId=config.DOC_ID).execute()
        task = _find_task(doc, item_text) or _find_mine(doc)
        if task is None:
            log.warning("no doc task to unclaim for: %r", item_text[:80])
            return False
        ranges = _marker_ranges(doc, task, config.INSTANCE_ID)
        if not ranges:
            return True  # nothing to remove
        deletes = [{"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}}
                   for start, end in sorted(ranges, reverse=True)]
        if _cas_update(service, doc, deletes):
            log.info("removed claim marker for: %r", item_text[:80])
            return True
    log.warning("could not unclaim after %d attempts (doc busy): %r",
                CAS_ATTEMPTS, item_text[:80])
    return False


def has_item(item_text: str) -> bool:
    """Whether item_text exists among ALL tasks, pending or struck through."""
    doc = _docs_service().documents().get(documentId=config.DOC_ID).execute()
    return any(_same_item(t["text"], item_text) for t in _tasks(doc))


def add_item(item_text: str) -> None:
    """Append item_text as a new top-level bullet: after the last task of the configured
    section when DOC_SECTION is set (so it is pickable), else at the end of the doc."""
    service = _docs_service()
    doc = service.documents().get(documentId=config.DOC_ID).execute()
    in_section = [t for t in _tasks(doc) if _in_section(t)]
    if config.DOC_SECTION and in_section:
        # Right after the section's last task (its last paragraph's end index).
        index = max(end for t in in_section for _s, end in t["ranges"])
    else:
        # Before the document's always-present trailing newline, so the new paragraph
        # lands at the end without disturbing the doc's final empty paragraph.
        index = doc["body"]["content"][-1]["endIndex"] - 1
    text = f"{item_text}\n"
    service.documents().batchUpdate(
        documentId=config.DOC_ID,
        body={"requests": [
            {"insertText": {"location": {"index": index}, "text": text}},
            {"createParagraphBullets": {
                "range": {"startIndex": index, "endIndex": index + _utf16_len(text)},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
        ]},
    ).execute()
    log.info("added backlog item: %r", item_text[:80])


def ensure_item(item_text: str) -> bool:
    """Add item_text as a pending backlog item unless an equivalent one (pending or
    done) already exists. Returns True if it was added."""
    if has_item(item_text):
        return False
    add_item(item_text)
    return True


def hold_task(item_text: str, item_id: str | None = None) -> bool:
    """Replace this instance's claim marker with an [on hold: <instance>] marker so no
    instance picks the task until CONTINUE. False when the task could not be found."""
    marker = f" [on hold: {config.INSTANCE_ID}]"
    service = _docs_service()
    for _attempt in range(CAS_ATTEMPTS):
        doc = service.documents().get(documentId=config.DOC_ID).execute()
        task = _find_task(doc, item_text) or _find_mine(doc)
        if task is None or task["struck"]:
            log.warning("no unstruck doc task to put on hold for: %r", item_text[:80])
            return False
        if held_by(task["text"]) == config.INSTANCE_ID:
            return True
        requests = [{"deleteContentRange": {"range": {"startIndex": s, "endIndex": e}}}
                    for s, e in sorted(_marker_ranges(doc, task, pattern=_MARKER_RE),
                                       reverse=True)]
        # Deletions run first (deepest-first), so the insert index must account for
        # the removed text before it on the same line; insert before them instead by
        # placing it at the line end computed AFTER deletions: simplest is two writes.
        if requests and _cas_update(service, doc, requests):
            continue  # re-read and insert on a clean line next attempt
        if requests:
            continue  # doc changed; retry
        insert = {"insertText": {"location": {"index": task["ranges"][0][1] - 1},
                                 "text": marker}}
        if _cas_update(service, doc, [insert]):
            log.info("put backlog task on hold for %s: %r", config.INSTANCE_ID, item_text[:80])
            return True
    log.warning("could not put task on hold after %d attempts: %r", CAS_ATTEMPTS, item_text[:80])
    return False


def unhold_task(item_text: str, item_id: str | None = None) -> bool:
    """Remove this instance's hold marker (the caller then claims the task as usual)."""
    service = _docs_service()
    for _attempt in range(CAS_ATTEMPTS):
        doc = service.documents().get(documentId=config.DOC_ID).execute()
        task = _find_task(doc, item_text)
        if task is None:
            log.warning("no doc task to take off hold for: %r", item_text[:80])
            return False
        ranges = _marker_ranges(doc, task, config.INSTANCE_ID, pattern=HOLD_RE)
        if not ranges:
            return True
        deletes = [{"deleteContentRange": {"range": {"startIndex": s, "endIndex": e}}}
                   for s, e in sorted(ranges, reverse=True)]
        if _cas_update(service, doc, deletes):
            log.info("took backlog task off hold: %r", item_text[:80])
            return True
    log.warning("could not take task off hold after %d attempts: %r", CAS_ATTEMPTS, item_text[:80])
    return False


def mark_done(item_text: str, item_id: str | None = None) -> bool:
    """Strike through the task matching item_text, sub-bullets included, and drop its
    claim markers (the strikethrough itself now marks it done). False if not found."""
    service = _docs_service()
    for _attempt in range(CAS_ATTEMPTS):
        doc = service.documents().get(documentId=config.DOC_ID).execute()
        task = _find_task(doc, item_text)
        if task is None:
            task = _find_mine(doc)
            if task is not None:
                log.warning("item text matches no bullet; striking the one carrying "
                            "our claim marker instead (bullet was probably edited): %r",
                            task["text"][:80])
        if task is None:
            log.warning("no doc task matched item text: %r", item_text[:80])
            return False
        if task["struck"]:
            log.info("item already struck through: %r", item_text[:80])
            return True
        log.info("striking through %d paragraph(s) for: %r",
                 len(task["ranges"]), item_text[:80])
        # Styling never shifts text, so the strike ranges stay valid across the batch;
        # the marker deletions DO shift text, so they run last, deepest-first.
        requests = [
            {
                "updateTextStyle": {
                    # end - 1 excludes the trailing newline of the paragraph
                    "range": {"startIndex": start, "endIndex": end - 1},
                    "textStyle": {"strikethrough": True},
                    "fields": "strikethrough",
                }
            }
            for start, end in task["ranges"]
        ] + [
            {"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}}
            for start, end in sorted(_marker_ranges(doc, task, pattern=_MARKER_RE),
                                     reverse=True)
        ]
        if _cas_update(service, doc, requests):
            return True
    log.warning("could not mark done after %d attempts (doc busy): %r",
                CAS_ATTEMPTS, item_text[:80])
    return False


def note_pr(item_text: str, item_id: str | None, pr_url: str) -> None:
    """The doc has no per-item link to write back; the user gets the PR by email."""


_SCOPE_HINT = ("posting comments on the doc needs the full Drive scope; re-run "
               "scripts/setup_oauth.py on the host to grant it (data/token.json was "
               "issued with the old read-only scope)")


def note_activity(item_text: str, item_id: str | None, message: str,
                  ref: str | None = None) -> str | None:
    """Append a note to the task's comment thread on the doc. The Drive API cannot
    anchor a comment to a bullet, so the thread is a doc-level comment that quotes
    the item text; `ref` is that comment's id. The first call creates the comment,
    later calls reply to it; a reply to a comment that was deleted or resolved starts
    a new thread and returns the new id."""
    service = _drive_service()
    try:
        if ref:
            try:
                service.comments().replies().create(
                    fileId=config.DOC_ID, commentId=ref, fields="id",
                    body={"content": message}).execute()
                return ref
            except HttpError as err:
                if err.resp.status != 404:
                    raise
                log.info("doc comment %s is gone (deleted/resolved); starting a new thread", ref)
        created = service.comments().create(
            fileId=config.DOC_ID, fields="id",
            body={"content": message,
                  "quotedFileContent": {"value": item_text, "mimeType": "text/plain"}},
        ).execute()
        log.info("started activity thread %s on the doc for: %r", created["id"], item_text[:80])
        return created["id"]
    except HttpError as err:
        if err.resp.status == 403:
            raise RuntimeError(f"Drive comment rejected (403): {_SCOPE_HINT}") from err
        raise


def validate() -> None:
    """Startup check for the doc backend (the doc itself is read lazily)."""
    if not config.DOC_ID:
        raise RuntimeError("CODEBOT_DOC_ID must be set in .env (the backlog Google Doc id)")
    if config.ACTIVITY_TRAIL:
        log.info("activity trail on: task notes are posted as comment threads on the doc "
                 "(if a 403 appears, %s)", _SCOPE_HINT)


def describe() -> str:
    return f"doc={config.DOC_ID}"
