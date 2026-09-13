"""The backlog codebot works: one of several backends behind a single interface.

Mirrors agent_runner's dispatch on a config string. main.py calls only this module;
the backend is chosen by CODEBOT_TASK_SOURCE ("gdoc" for the Google Doc, "github" for
a GitHub Projects v2 board). Imports are lazy so a GitHub deployment never needs the
Google libraries importable and vice versa.

Every backend exposes the same functions, with the same semantics:

  list_pending_items() -> [{"id", "text", "detail", "images", "claimed_by_me",
                            "priority", "url"}]
  claim_task / unclaim_task / hold_task / unhold_task / mark_done(text, item_id=None)
  ensure_item(text) -> bool           # seed an item unless an equivalent exists
  note_pr(text, item_id, pr_url)      # link the PR to the item (no-op for the doc)
  note_activity(text, item_id, message, ref=None) -> ref
                                      # append a note to the item's activity trail
  validate()                          # startup checks; raises RuntimeError
  describe() -> str                   # "doc=<id>" / "project=<owner>/<n>" for logs

Activity trail: main.trail() posts a plain-text note at every task milestone. The
backend decides where notes live — GitHub: issue comments (ref is None); Google
Doc: one comment thread per task, the first note creates a comment quoting the item
and later notes reply to it (ref is the Drive comment id); a JIRA backend would use
issue comments. `ref` is opaque: the caller stores whatever the first call returned
(state["trail_ref"]) and passes it back on later calls.

"text" is the identity the FSM carries (state["item"]) and the PICK contract copies
verbatim; "id" is the backend's own identity ("" for the doc, the project item node
id for GitHub), carried alongside as state["item_id"] and preferred by backends that
have one. Every backend accepts an identity-less call and matches on text.
"""
import config
from task_text import normalize  # noqa: F401 — part of the façade's surface

SOURCES = ("gdoc", "github")


def _impl():
    if config.TASK_SOURCE == "gdoc":
        import gdoc_client
        return gdoc_client
    if config.TASK_SOURCE == "github":
        import github_projects_client
        return github_projects_client
    raise RuntimeError(f"unsupported CODEBOT_TASK_SOURCE: {config.TASK_SOURCE!r} "
                       f"(expected one of {', '.join(SOURCES)})")


def list_pending_items() -> list[dict]:
    return _impl().list_pending_items()


def claim_task(item_text: str, item_id: str | None = None) -> bool:
    return _impl().claim_task(item_text, item_id=item_id)


def unclaim_task(item_text: str, item_id: str | None = None) -> bool:
    return _impl().unclaim_task(item_text, item_id=item_id)


def hold_task(item_text: str, item_id: str | None = None) -> bool:
    return _impl().hold_task(item_text, item_id=item_id)


def unhold_task(item_text: str, item_id: str | None = None) -> bool:
    return _impl().unhold_task(item_text, item_id=item_id)


def mark_done(item_text: str, item_id: str | None = None) -> bool:
    return _impl().mark_done(item_text, item_id=item_id)


def ensure_item(item_text: str) -> bool:
    return _impl().ensure_item(item_text)


def note_pr(item_text: str, item_id: str | None, pr_url: str) -> None:
    _impl().note_pr(item_text, item_id, pr_url)


def note_activity(item_text: str, item_id: str | None, message: str,
                  ref: str | None = None) -> str | None:
    return _impl().note_activity(item_text, item_id, message, ref=ref)


def validate() -> None:
    _impl().validate()


def describe() -> str:
    return _impl().describe()
