import os
from pathlib import Path

from . import kb
from .db import get_db, init_db
from .util import dumps, loads, new_uid, now_iso, rows_to_dicts

TRANSITIONS = {
    ("theory", "theory_done"): "check",
    ("check", "next_block"): "theory",
    ("check", "go_practice"): "practice",
    ("practice", "practice_done"): "debrief",
}

LOG_EVENTS = {"ask", "answer", "note", "practice_log"}


def create_course(topic: str, plan: dict | None = None) -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO courses(topic, status, plan_json, created_at) VALUES (?,?,?,?)",
            (topic, "planned", dumps(plan or {}), now_iso()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "topic": topic, "status": "planned", "plan": plan or {}}
    finally:
        conn.close()


def list_courses() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def add_source(course_id: int, kind: str, title: str, url: str | None = None, local_path: str | None = None) -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO sources(course_id, kind, title, url, local_path, status) VALUES (?,?,?,?,?, 'chosen')",
            (course_id, kind, title, url, local_path),
        )
        conn.commit()
        return {"id": cur.lastrowid, "course_id": course_id, "kind": kind, "title": title, "status": "chosen"}
    finally:
        conn.close()


def list_sources(course_id: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM sources WHERE course_id = ? ORDER BY id", (course_id,)).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def start_session(course_id: int) -> dict:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE course_id = ?", (course_id,)
        ).fetchone()
        idx = row["n"] + 1
        cur = conn.execute(
            "INSERT INTO sessions(course_id, idx, status, state, started_at) VALUES (?,?, 'active', 'theory', ?)",
            (course_id, idx, now_iso()),
        )
        conn.commit()
        return get_session(cur.lastrowid)
    finally:
        conn.close()


def get_session(session_id: int) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return {"error": f"session {session_id} not found"}
        s = dict(row)
        s["transcript"] = loads(s.pop("transcript_json"), [])
        allowed = sorted({ev for (st, ev) in TRANSITIONS if st == s["state"]})
        if s["state"] == "debrief":
            allowed.append("finish_session")
        s["allowed_events"] = allowed
        return s
    finally:
        conn.close()


def advance(session_id: int, event: str, payload: dict | None = None) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return {"error": f"session {session_id} not found"}
        if row["status"] != "active":
            return {"error": f"session is {row['status']}, advance denied"}

        state = row["state"]
        transcript = loads(row["transcript_json"], [])
        transcript.append({"ts": now_iso(), "state": state, "event": event, "payload": payload or {}})

        new_state = TRANSITIONS.get((state, event))
        if new_state is None and event not in LOG_EVENTS:
            allowed = sorted({ev for (st, ev) in TRANSITIONS if st == state})
            return {"error": f"event '{event}' invalid in state '{state}'", "allowed_events": allowed}

        if new_state:
            conn.execute(
                "UPDATE sessions SET state = ?, transcript_json = ? WHERE id = ?",
                (new_state, dumps(transcript), session_id),
            )
        else:
            conn.execute("UPDATE sessions SET transcript_json = ? WHERE id = ?", (dumps(transcript), session_id))
        conn.commit()
        return get_session(session_id)
    finally:
        conn.close()


def finish_session(session_id: int, block: dict) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return {"error": f"session {session_id} not found"}
        if row["state"] != "debrief":
            return {"error": "finish allowed only from state 'debrief'", "state": row["state"]}
        if row["status"] != "active":
            return {"error": f"session already {row['status']}"}

        block_uid, path = kb.write_block(row["course_id"], block)
        ended = now_iso()
        conn.execute(
            "UPDATE sessions SET status = 'finished', state = 'done', ended_at = ?, transcript_json = ? WHERE id = ?",
            (ended, row["transcript_json"], session_id),
        )
        cur = conn.execute(
            "INSERT INTO blocks(course_id, session_id, block_uid, title, path, tags_json, sources_json, review_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                row["course_id"],
                session_id,
                block_uid,
                block.get("title", "Без названия"),
                path,
                dumps(block.get("tags", [])),
                dumps(block.get("sources", [])),
                dumps({"ease": 2.5, "interval": 1, "due": None}),
                ended,
            ),
        )
        conn.commit()
        return {"ok": True, "block_id": cur.lastrowid, "block_uid": block_uid, "path": os.path.relpath(path)}
    finally:
        conn.close()


def list_blocks(course_id: int | None = None) -> list[dict]:
    conn = get_db()
    try:
        if course_id:
            rows = conn.execute("SELECT * FROM blocks WHERE course_id = ? ORDER BY id DESC", (course_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM blocks ORDER BY id DESC").fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def get_block(block_uid: str) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM blocks WHERE block_uid = ?", (block_uid,)).fetchone()
        if not row:
            return {"error": f"block {block_uid} not found"}
        b = dict(row)
        b["tags"] = loads(b.pop("tags_json"), [])
        b["sources"] = loads(b.pop("sources_json"), [])
        b["review"] = loads(b.pop("review_json"), {})
        b["content"] = kb.read_block(b["path"])
        return b
    finally:
        conn.close()
