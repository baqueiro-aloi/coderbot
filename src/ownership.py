"""Stable instance identity and conservative recovery of pre-fingerprint markers."""
import json

import config
from task_text import normalize


def me() -> str:
    return f"{config.INSTANCE_ID}@{config.INSTANCE_FINGERPRINT}"


def locally_owned(item_text: str, item_id: str | None = None) -> bool:
    """Adopt legacy name-only markers only with corroborating local task state."""
    records = []
    try:
        records.append(json.loads(config.STATE_PATH.read_text()))
    except (OSError, ValueError):
        pass
    try:
        records.extend(json.loads(config.HOLDS_PATH.read_text()))
    except (OSError, ValueError):
        pass
    for record in records:
        if item_id and record.get("item_id"):
            if record["item_id"] == item_id:
                return True
        elif normalize(record.get("item", "")) == normalize(item_text):
            return True
    return False


def mine(owner: str | None, item_text: str, item_id: str | None = None) -> bool:
    return bool(owner == me() or
                (owner == config.INSTANCE_ID and locally_owned(item_text, item_id)))


def legacy_marker(owner: str | None, item_text: str, item_id: str | None = None) -> bool:
    return owner == config.INSTANCE_ID and locally_owned(item_text, item_id)
