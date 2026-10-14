"""Переход на схему v2: модульные таблицы + перенос данных + kb/ в kb/blocks/.

Revision ID: 0002_v2
Revises: 0001_baseline
Create Date: 2026-10-13

Шаги (ТЗ 03): бэкап БД → stamp baseline для существующей → новые таблицы →
перенос sources/chapters/sessions/blocks/courses → kb/*.md → kb/blocks/ (frontmatter v2) →
categories.yaml + индекс → settings.profile.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0002_v2"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
  title TEXT NOT NULL, author TEXT, url TEXT, local_path TEXT,
  status TEXT NOT NULL DEFAULT 'chosen', summary TEXT,
  meta_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  idx INTEGER NOT NULL, title TEXT NOT NULL, path TEXT NOT NULL,
  tokens_est INTEGER, summary TEXT,
  key_points_json TEXT NOT NULL DEFAULT '[]', has_exercises INTEGER NOT NULL DEFAULT 0,
  UNIQUE(source_id, idx)
);
CREATE INDEX IF NOT EXISTS ix_chapters_source_id ON chapters_new (source_id);
CREATE TABLE IF NOT EXISTS categories (
  path TEXT PRIMARY KEY, title TEXT NOT NULL, parent_path TEXT, color TEXT, icon TEXT,
  sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS activities (
  id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
  source_id INTEGER NOT NULL REFERENCES sources(id), course_id INTEGER REFERENCES courses(id),
  title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
  cursor_chapter INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL DEFAULT 'Новый разговор', mode TEXT NOT NULL DEFAULT 'free',
  activity_id INTEGER REFERENCES activities(id), chapter_idx INTEGER, focus_block_uid TEXT,
  summary TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
  tool_calls_json TEXT, tool_call_id TEXT, tool_name TEXT, cards_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_conversation ON messages (conversation_id, id);
CREATE TABLE IF NOT EXISTS sessions_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
  conversation_id INTEGER REFERENCES conversations(id),
  activity_id INTEGER REFERENCES activities(id), course_id INTEGER REFERENCES courses(id),
  chapter_idx INTEGER, idx INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
  state TEXT NOT NULL DEFAULT 'theory', config_json TEXT NOT NULL DEFAULT '{}',
  started_at TEXT NOT NULL, ended_at TEXT, transcript_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS blocks_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT, block_uid TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'lesson', title TEXT NOT NULL, summary TEXT,
  category_path TEXT, category_status TEXT NOT NULL DEFAULT 'suggested', path TEXT NOT NULL,
  session_uid TEXT, conversation_uid TEXT, activity_uid TEXT,
  weak_spots_count INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
  review_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_blocks_category_path ON blocks_new (category_path);
CREATE INDEX IF NOT EXISTS ix_blocks_updated_at ON blocks_new (updated_at);
CREATE TABLE IF NOT EXISTS block_tags (block_uid TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(block_uid, tag));
CREATE INDEX IF NOT EXISTS ix_block_tags_tag ON block_tags (tag);
CREATE TABLE IF NOT EXISTS block_sources (block_uid TEXT NOT NULL, source_uid TEXT NOT NULL, chapter_idx INTEGER);
CREATE INDEX IF NOT EXISTS ix_block_sources_source_uid ON block_sources (source_uid);
CREATE TABLE IF NOT EXISTS block_links (from_uid TEXT NOT NULL, to_uid TEXT NOT NULL, PRIMARY KEY(from_uid, to_uid));
CREATE TABLE IF NOT EXISTS block_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, block_uid TEXT NOT NULL, version INTEGER NOT NULL,
  content TEXT NOT NULL, reason TEXT, conversation_uid TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS courses_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
  topic TEXT NOT NULL, description TEXT, category_path TEXT,
  status TEXT NOT NULL DEFAULT 'planned', plan_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS course_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id INTEGER NOT NULL REFERENCES courses(id), position INTEGER NOT NULL,
  item_type TEXT NOT NULL, source_id INTEGER REFERENCES sources(id),
  chapter_idx INTEGER, block_uid TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, target TEXT,
  status TEXT NOT NULL DEFAULT 'queued', progress INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0, message TEXT, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, provider TEXT NOT NULL,
  model TEXT NOT NULL, conversation_uid TEXT, status TEXT NOT NULL,
  steps INTEGER NOT NULL DEFAULT 0, tool_calls INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER, output_tokens INTEGER, duration_ms INTEGER, error TEXT,
  created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
  block_uid UNINDEXED, title, summary, body, tags,
  tokenize='unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
  chapter_id UNINDEXED, source_uid UNINDEXED, title, body,
  tokenize='unicode61 remove_diacritics 2'
);
"""

DEFAULT_PROFILE = """{
  "name": "Дмитрий",
  "about": "DevOps, люблю объяснения через аналогии",
  "machines": [
    {"id": "mac", "name": "MacBook", "kind": "macos", "specs": "M-series, 32 GB",
     "tools": ["brew", "docker", "uv", "node"], "notes": ""},
    {"id": "homelab", "name": "Хомлаб", "kind": "proxmox",
     "specs": "Proxmox 192.168.0.105, LXC со статическими IP", "tools": ["pct", "docker"],
     "notes": "спит 19:00–08:30"}
  ],
  "learning": {"session_minutes": 30, "theory_concepts": 5, "questions_per_concept": 1,
               "practice_default": true, "explain_style": "аналогии + пример из DevOps"}
}"""

START_CATEGORIES = """- path: programming
  title: Программирование
  color: sky
  icon: code
  children:
    - path: programming/python
      title: Python
      children:
        - {path: programming/python/oop, title: ООП}
- path: infra
  title: Инфраструктура
  color: emerald
  icon: server
  children:
    - {path: infra/kubernetes, title: Kubernetes}
- path: life
  title: Личное
  color: amber
  icon: heart
  children:
    - {path: life/cooking, title: Кулинария, icon: chef-hat}
"""

CATEGORY_ROWS = [
    ("programming", "Программирование", None),
    ("programming/python", "Python", "programming"),
    ("programming/python/oop", "ООП", "programming/python"),
    ("infra", "Инфраструктура", None),
    ("infra/kubernetes", "Kubernetes", "infra"),
    ("life", "Личное", None),
    ("life/cooking", "Кулинария", "life"),
]


def _swap(bind, old: str, new: str) -> None:
    """Переименовать new→old-имя, не трогая FK-ссылки других таблиц (legacy_alter_table)."""
    bind.exec_driver_sql("PRAGMA legacy_alter_table=ON")
    bind.exec_driver_sql(f"ALTER TABLE {old} RENAME TO {old}_old")
    bind.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
    bind.exec_driver_sql(f"ALTER TABLE {new} RENAME TO {old}")
    bind.exec_driver_sql(f"DROP TABLE {old}_old")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _uid(prefix: str, used: set) -> str:
    import secrets

    while True:
        uid = f"{prefix}_{secrets.token_hex(4)}"
        if uid not in used:
            used.add(uid)
            return uid


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Бэкап существующей БД
    db_path = bind.engine.url.database
    if db_path and Path(db_path).exists():
        import shutil

        src = Path(db_path)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(src, src.with_name(f"{src.name}.bak-{stamp}"))

    # stamp не нужен: 0001 идемпотентен (IF NOT EXISTS), а v1 определяется ниже по колонкам
    # (command.stamp внутри активной миграции блокирует SQLite)

    # 2. Новая схема (идемпотентно; по одному стейтменту — sqlite3 не умеет несколько за раз)
    for stmt in filter(None, (s.strip() for s in V2_SCHEMA.split(";"))):
        bind.exec_driver_sql(stmt)

    now = _now()
    source_uid: dict[int, str] = {}
    session_uid: dict[int, str] = {}
    used: set = set()

    v1_sources = "sources" in tables and "uid" not in {c["name"] for c in inspector.get_columns("sources")}
    if v1_sources:
        # 3. sources → +uid; главы переносятся с сохранением source_id
        for r in bind.execute(sa.text("SELECT * FROM sources")).mappings().all():
            uid = _uid("src", used)
            source_uid[r["id"]] = uid
            bind.execute(
                sa.text(
                    "INSERT INTO sources_new (uid, kind, title, url, local_path, status, meta_json, created_at, updated_at) "
                    "VALUES (:u, :k, :t, :url, :lp, :st, :mj, :ca, :ua)"
                ),
                {
                    "u": uid,
                    "k": r["kind"],
                    "t": r["title"],
                    "url": r["url"],
                    "lp": r["local_path"],
                    "st": r["status"],
                    "mj": r["meta_json"] or "{}",
                    "ca": now,
                    "ua": now,
                },
            )
            if r["course_id"]:
                bind.execute(
                    sa.text(
                        "INSERT INTO course_items (course_id, position, item_type, source_id) VALUES (:c, (SELECT COALESCE(MAX(position),0)+1 FROM course_items WHERE course_id=:c), 'source', :s)"
                    ),
                    {"c": r["course_id"], "s": r["id"]},
                )
        bind.execute(
            sa.text(
                "INSERT INTO chapters_new (source_id, idx, title, path, tokens_est, summary) "
                "SELECT source_id, idx, title, path, tokens_est, summary FROM chapters"
            )
        )
        bind.exec_driver_sql("DROP TABLE chapters")
        bind.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        bind.exec_driver_sql("ALTER TABLE chapters_new RENAME TO chapters")
        bind.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
        _swap(bind, "sources", "sources_new")

    v1_courses = "courses" in tables and "uid" not in {c["name"] for c in inspector.get_columns("courses")}
    if v1_courses:
        # 4. courses: topic → title и topic, +uid
        for r in bind.execute(sa.text("SELECT * FROM courses")).mappings().all():
            uid = _uid("crs", used)
            bind.execute(
                sa.text(
                    "INSERT INTO courses_new (uid, title, topic, status, plan_json, created_at, updated_at) VALUES (:u, :t, :t, :st, :pj, :ca, :ua)"
                ),
                {
                    "u": uid,
                    "t": r["topic"],
                    "st": r["status"],
                    "pj": r["plan_json"] or "{}",
                    "ca": r["created_at"] or now,
                    "ua": now,
                },
            )
        _swap(bind, "courses", "courses_new")

    v1_sessions = "sessions" in tables and "uid" not in {c["name"] for c in inspector.get_columns("sessions")}
    if v1_sessions:
        # 5. sessions: +uid (course_id остаётся)
        for r in bind.execute(sa.text("SELECT * FROM sessions")).mappings().all():
            uid = _uid("ses", used)
            session_uid[r["id"]] = uid
            bind.execute(
                sa.text(
                    "INSERT INTO sessions_new (uid, course_id, idx, status, state, started_at, ended_at, transcript_json) VALUES (:u, :c, :i, :st, :state, :sa, :ea, :tj)"
                ),
                {
                    "u": uid,
                    "c": r["course_id"],
                    "i": r["idx"],
                    "st": r["status"],
                    "state": r["state"],
                    "sa": r["started_at"],
                    "ea": r["ended_at"],
                    "tj": r["transcript_json"] or "[]",
                },
            )
        _swap(bind, "sessions", "sessions_new")

    v1_blocks = "blocks" in tables and "kind" not in {c["name"] for c in inspector.get_columns("blocks")}
    if v1_blocks:
        # 6. blocks v1 → v2: kind=lesson, session_id → session_uid
        import json

        for r in bind.execute(sa.text("SELECT * FROM blocks")).mappings().all():
            suid = session_uid.get(r["session_id"]) if r["session_id"] else None
            bind.execute(
                sa.text(
                    "INSERT INTO blocks_new (block_uid, kind, title, path, session_uid, review_json, created_at, updated_at) "
                    "VALUES (:bu, 'lesson', :t, :p, :su, :rj, :ca, :ua)"
                ),
                {
                    "bu": r["block_uid"],
                    "t": r["title"],
                    "p": r["path"],
                    "su": suid,
                    "rj": r["review_json"] or "{}",
                    "ca": r["created_at"] or now,
                    "ua": now,
                },
            )
            for tag in json.loads(r["tags_json"] or "[]"):
                bind.execute(
                    sa.text("INSERT OR IGNORE INTO block_tags (block_uid, tag) VALUES (:bu, :t)"),
                    {"bu": r["block_uid"], "t": str(tag)},
                )
        _swap(bind, "blocks", "blocks_new")

    # 7–9. kb/*.md → kb/blocks/ с frontmatter v2; categories.yaml; settings.profile
    kb_dir = _kb_dir(bind)
    if kb_dir is not None:
        import re

        blocks_dir = kb_dir / "blocks"
        blocks_dir.mkdir(exist_ok=True)
        for md in sorted(kb_dir.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            m = re.search(r"^id:\s*(blk_\w+)", text, re.M)
            uid = m.group(1) if m else md.stem.split("_")[0]
            target = blocks_dir / md.name
            if not target.exists():
                target.write_text(_rewrite_frontmatter(text, uid, now), encoding="utf-8")
            md.unlink()
        cats = kb_dir / "categories.yaml"
        if not cats.exists():
            cats.write_text(START_CATEGORIES, encoding="utf-8")

    bind.execute(
        sa.text("INSERT OR IGNORE INTO settings (key, value_json) VALUES ('profile', :p)"),
        {"p": DEFAULT_PROFILE},
    )
    for path, title, parent in CATEGORY_ROWS:
        bind.execute(
            sa.text("INSERT OR IGNORE INTO categories (path, title, parent_path) VALUES (:p, :t, :parent)"),
            {"p": path, "t": title, "parent": parent},
        )


def _kb_dir(bind):
    """Каталог kb/ из env или рядом с БД (repo/kb)."""
    import os

    env = os.environ.get("LEARNOS_KB_DIR")
    if env:
        return Path(env)
    db_path = bind.engine.url.database
    if db_path:
        kb = Path(db_path).resolve().parent.parent / "kb"
        if kb.exists():
            return kb
    return None


def _rewrite_frontmatter(text: str, uid: str, now: str) -> str:
    """Frontmatter v1 → v2: kind, category, category_status, version, даты; course убирается."""
    import yaml

    parts = text.split("---", 2)
    if len(parts) < 3:
        fm: dict = {}
        body = text
    else:
        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2]
    fm.pop("course", None)
    fm["id"] = uid
    fm.setdefault("kind", "lesson")
    fm.setdefault("summary", "")
    fm["category"] = fm.get("category")
    fm["category_status"] = "suggested"
    fm.setdefault("created", now)
    fm.setdefault("updated", now)
    fm["version"] = 1
    fm["review"] = fm.get("review") or {"ease": 2.5, "interval": 1, "due": None}
    return f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()}\n---\n{body}"


def downgrade() -> None:
    pass
