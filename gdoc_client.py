"""Read pending improvements from the Google Doc and strike items through when done."""
import logging
import re

from googleapiclient.discovery import build

import config
from google_auth import load_credentials

log = logging.getLogger(__name__)


def _docs_service():
    return build("docs", "v1", credentials=load_credentials(), cache_discovery=False)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _iter_paragraphs(document: dict):
    """Yield (text, start_index, end_index, fully_struck) per paragraph."""
    for element in document.get("body", {}).get("content", []):
        para = element.get("paragraph")
        if not para:
            continue
        text_parts = []
        runs = []
        for pe in para.get("elements", []):
            run = pe.get("textRun")
            if not run:
                continue
            content = run.get("content", "")
            if content.strip():
                runs.append(run)
            text_parts.append(content)
        text = "".join(text_parts).strip()
        if not text or not runs:
            continue
        struck = all(run.get("textStyle", {}).get("strikethrough") for run in runs)
        if "startIndex" not in element or "endIndex" not in element:
            continue
        yield text, element["startIndex"], element["endIndex"], struck


def list_pending_items() -> list[str]:
    """Non-empty paragraphs/list items whose text is not fully struck through."""
    doc = _docs_service().documents().get(documentId=config.DOC_ID).execute()
    items = [text for text, _s, _e, struck in _iter_paragraphs(doc) if not struck]
    log.debug("doc %s: %d pending item(s)", config.DOC_ID, len(items))
    return items


def has_item(item_text: str) -> bool:
    """Whether item_text exists among ALL paragraphs, pending or struck through."""
    doc = _docs_service().documents().get(documentId=config.DOC_ID).execute()
    target = _normalize(item_text)
    return any(_normalize(text) == target for text, _s, _e, _struck in _iter_paragraphs(doc))


def add_item(item_text: str) -> None:
    """Append item_text as a new pending paragraph at the end of the document."""
    service = _docs_service()
    doc = service.documents().get(documentId=config.DOC_ID).execute()
    # Insert before the document's always-present trailing newline, so the new
    # paragraph lands at the end without disturbing the doc's final empty paragraph.
    end_index = doc["body"]["content"][-1]["endIndex"]
    service.documents().batchUpdate(
        documentId=config.DOC_ID,
        body={
            "requests": [
                {"insertText": {"location": {"index": end_index - 1}, "text": f"{item_text}\n"}}
            ]
        },
    ).execute()


def ensure_item(item_text: str) -> bool:
    """Add item_text as a pending backlog item unless an equivalent one (pending or
    done) already exists. Returns True if it was added."""
    if has_item(item_text):
        return False
    add_item(item_text)
    return True


def mark_done(item_text: str) -> bool:
    """Strike through the paragraph matching item_text. Returns False if not found."""
    service = _docs_service()
    doc = service.documents().get(documentId=config.DOC_ID).execute()
    target = _normalize(item_text)
    for text, start, end, struck in _iter_paragraphs(doc):
        if _normalize(text) == target:
            if struck:
                log.info("item already struck through: %r", item_text[:80])
                return True
            log.info("striking through doc range [%d,%d): %r", start, end - 1, item_text[:80])
            service.documents().batchUpdate(
                documentId=config.DOC_ID,
                body={
                    "requests": [
                        {
                            "updateTextStyle": {
                                # end - 1 excludes the trailing newline of the paragraph
                                "range": {"startIndex": start, "endIndex": end - 1},
                                "textStyle": {"strikethrough": True},
                                "fields": "strikethrough",
                            }
                        }
                    ]
                },
            ).execute()
            return True
    log.warning("no doc paragraph matched item text: %r", item_text[:80])
    return False
