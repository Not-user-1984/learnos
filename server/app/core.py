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


def process_source(source_id: int) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            return {"error": f"source {source_id} not found"}
        if row["status"] == "processed":
            return {"ok": True, "note": "already processed", "chapters": list_chapters(source_id)}
        kind, url = row["kind"], row["url"]
    finally:
        conn.close()

    from . import skills_loader

    if kind == "book":
        return skills_loader.run_skill("book-splitter", {"source_id": source_id})
    if kind == "video" and url:
        res = skills_loader.run_skill("youtube-to-summary", {"url": url})
        if res.get("ok"):
            path = Path(res["path"])
            text_len = path.stat().st_size
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO chapters(source_id, idx, title, path, tokens_est, summary) VALUES (?,?,?,?,?,?)",
                    (source_id, 1, res.get("title", url), str(path), max(1, text_len // 4), res.get("preview", "")[:280]),
                )
                conn.execute("UPDATE sources SET status = 'processed', meta_json = ? WHERE id = ?",
                             (dumps({"video_id": res.get("video_id"), "lang": res.get("lang")}), source_id))
                conn.commit()
            finally:
                conn.close()
        return res
    return {"error": f"не знаю, как обрабатывать kind='{kind}' (нужен url для video или local_path для book)"}


def list_chapters(source_id: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT idx, title, path, tokens_est, summary FROM chapters WHERE source_id = ? ORDER BY idx",
            (source_id,),
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


def read_chapter(source_id: int, chapter: int, offset: int = 0, limit: int = 12000) -> dict:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM chapters WHERE source_id = ? AND idx = ?", (source_id, chapter)
        ).fetchone()
        if not row:
            return {"error": f"chapter {chapter} of source {source_id} not found"}
    finally:
        conn.close()
    text = Path(row["path"]).read_text(encoding="utf-8")
    chunk = text[offset : offset + limit]
    return {
        "source_id": source_id,
        "idx": row["idx"],
        "title": row["title"],
        "total_chars": len(text),
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(text) else None,
        "text": chunk,
    }


def search_chunks(query: str, limit: int = 10) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT ch.source_id, ch.idx, ch.title, ch.path, s.title AS source_title "
            "FROM chapters ch JOIN sources s ON s.id = ch.source_id WHERE s.status = 'processed'"
        ).fetchall()
    finally:
        conn.close()
    needle = query.lower()
    hits = []
    for r in rows:
        try:
            text = Path(r["path"]).read_text(encoding="utf-8")
        except OSError:
            continue
        pos = text.lower().find(needle)
        if pos == -1:
            continue
        start = max(0, pos - 150)
        hits.append({
            "source_id": r["source_id"],
            "source_title": r["source_title"],
            "chapter": r["idx"],
            "chapter_title": r["title"],
            "snippet": text[start : pos + len(query) + 200].replace("\n", " "),
        })
        if len(hits) >= limit:
            break
    return hits


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
