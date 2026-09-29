"""Durable, bounded progress signals for STATUS (never stores agent reasoning).

Codebot owns agent_activity.sqlite. OpenCode owns opencode.db; the latter is read
only and optional so a separate watcher can see child-session progress in WAL.
"""
import json
import logging
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import config

log = logging.getLogger(__name__)


def _key(state: dict) -> str:
    return str(state.get("branch") or state.get("slug") or "")


def _database() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = config.DATA_DIR / "agent_activity.sqlite"
    fresh = not path.exists()
    db = sqlite3.connect(path, timeout=2)
    db.execute("PRAGMA busy_timeout=2000")
    if fresh:
        db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS turn (id INTEGER PRIMARY KEY CHECK(id=1), "
               "task_key TEXT NOT NULL, phase TEXT NOT NULL, session_id TEXT NOT NULL, "
               "started REAL NOT NULL, last_event REAL, activity TEXT NOT NULL, "
               "active INTEGER NOT NULL, pid INTEGER NOT NULL)")
    return db


def begin(state: dict, session_id: str = "") -> None:
    if not _key(state):
        return
    with closing(_database()) as db, db:
        db.execute("INSERT OR REPLACE INTO turn "
                   "(id,task_key,phase,session_id,started,last_event,activity,active,pid) "
                   "VALUES(1,?,?,?,?,?,?,1,?)",
                   (_key(state), str(state.get("state") or ""), session_id, time.time(),
                    None, "agent turn started", os.getpid()))


def observe(state: dict, *, activity: str | None = None,
            session_id: str | None = None, now: float | None = None) -> None:
    if not _key(state):
        return
    with closing(_database()) as db, db:
        db.execute("UPDATE turn SET last_event=?, activity=COALESCE(?,activity), "
                   "session_id=COALESCE(?,session_id) WHERE id=1 AND task_key=? AND active=1",
                   (now if now is not None else time.time(), activity, session_id, _key(state)))


def finish(state: dict) -> None:
    if not _key(state):
        return
    with closing(_database()) as db, db:
        db.execute("UPDATE turn SET active=0 WHERE id=1 AND task_key=?", (_key(state),))


def durable_turn(state: dict) -> dict:
    """Other processes read the last persisted turn without writing to its database."""
    path = config.DATA_DIR / "agent_activity.sqlite"
    if not path.is_file() or not _key(state):
        return {}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                                     timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute("SELECT phase,session_id,started,last_event,activity,active,pid "
                             "FROM turn WHERE id=1 AND task_key=?", (_key(state),)).fetchone()
        if not row:
            return {}
        return dict(zip(("phase", "session_id", "started_at", "last_activity",
                         "activity", "active", "pid"), row))
    except (OSError, sqlite3.Error):
        log.warning("could not read durable agent activity", exc_info=True)
        return {}


def _opencode_path() -> Path:
    xdg = Path(os.environ.get("XDG_DATA_HOME") or config.DATA_DIR / "opencode" / "data")
    return xdg / "opencode" / "opencode.db"


def _label(value: str, limit: int = 90) -> str:
    return " ".join(value.split())[:limit]


def opencode_progress(state: dict) -> dict:
    """Select metadata and short task titles only; never reasoning, prompts or output."""
    session_id = state.get("session_id")
    path = _opencode_path()
    if not isinstance(session_id, str) or not session_id or not path.is_file():
        return {}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                                     timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA busy_timeout=2000")
            if not db.execute("SELECT 1 FROM session WHERE id=?", (session_id,)).fetchone():
                return {}
            todos = db.execute("SELECT status,count(*) FROM todo WHERE session_id=? "
                               "GROUP BY status", (session_id,)).fetchall()
            current = db.execute("SELECT content FROM todo WHERE session_id=? AND "
                                 "status='in_progress' ORDER BY position LIMIT 1",
                                 (session_id,)).fetchone()
            family = db.execute(
                "WITH RECURSIVE family(id,depth) AS (SELECT ?,0 UNION ALL "
                "SELECT s.id,f.depth+1 FROM session s JOIN family f ON s.parent_id=f.id "
                "WHERE f.depth<3) SELECT s.id,s.title,s.time_updated,f.depth "
                "FROM family f JOIN session s ON s.id=f.id "
                "ORDER BY s.time_updated DESC LIMIT 30", (session_id,)).fetchall()
            events = []
            children = []
            for sid, title, updated, depth in family:
                row = db.execute("SELECT data,time_updated FROM part WHERE session_id=? "
                                 "ORDER BY time_updated DESC LIMIT 1", (sid,)).fetchone()
                if not row:
                    continue
                try:
                    part = json.loads(row[0])
                except (ValueError, TypeError):
                    continue
                if not isinstance(part, dict):
                    continue
                when = row[1] / 1000 if isinstance(row[1], (float, int)) else 0
                if when <= 0:
                    continue
                kind = part.get("type")
                tool = part.get("tool") if kind == "tool" else None
                raw_state = part.get("state")
                tool_state = raw_state if isinstance(raw_state, dict) else {}
                status = tool_state.get("status") if kind == "tool" else None
                event = {"at": when, "kind": kind, "tool": tool, "status": status}
                events.append(event)
                if depth:
                    # Session titles identify subagent assignments without exposing
                    # the child prompt, reasoning, shell command or tool output.
                    children.append({"title": _label(str(title or "subagent").split(" (@")[0]),
                                     **event})
        latest = max(events, key=lambda item: item["at"]) if events else None
        return {"todos": dict(todos), "current_task": _label(current[0]) if current else "",
                "children": sorted(children, key=lambda item: item["at"], reverse=True)[:2],
                "latest": latest}
    except (OSError, sqlite3.Error) as error:
        # OpenCode's own schema is not our contract; retain the durable fallback.
        log.warning("OpenCode progress metadata unavailable: %s", error)
        return {}


def snapshot(state: dict, turn: dict, now: float | None = None) -> dict:
    """Combine in-process, durable and OpenCode metadata, newest event wins."""
    result = dict(turn)
    saved = durable_turn(state)
    if saved:
        if not result.get("active"):
            result.update(saved)
            if result.get("active") and isinstance(result.get("pid"), int):
                try:
                    os.kill(result["pid"], 0)
                except ProcessLookupError:
                    result["active"] = False
                    result["process_dead"] = True
                except PermissionError:
                    pass  # Process is present but owned by another user.
        elif (saved.get("last_activity") or 0) > (result.get("last_activity") or 0):
            result["last_activity"] = saved["last_activity"]
            result["activity"] = saved["activity"]
        if saved.get("active") and saved.get("session_id") and not result.get("session_id"):
            result["session_id"] = saved["session_id"]
    if config.AGENT == "opencode":
        session_id = result.get("session_id") or state.get("session_id")
        progress = opencode_progress({**state, "session_id": session_id})
        result.update(progress)
        last = progress.get("latest") or {}
        if (last.get("at") or 0) > (result.get("last_activity") or 0):
            result["last_activity"] = last["at"]
            if progress.get("children") and progress["children"][0]["at"] == last["at"]:
                result["activity"] = "subagent: " + progress["children"][0]["title"]
            elif last.get("tool"):
                result["activity"] = "tool: " + str(last["tool"])[:35]
            else:
                result["activity"] = "agent step"  # never expose reasoning text
    return result
