"""Базовая ревизия = схема v1 (до модульного ядра).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-13

Существующая БД без alembic_version получает stamp этой ревизии (см. 0002).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    plan_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    local_path TEXT,
    status TEXT NOT NULL DEFAULT 'found',
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    tokens_est INTEGER,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    idx INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    state TEXT NOT NULL DEFAULT 'theory',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    transcript_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    session_id INTEGER REFERENCES sessions(id),
    block_uid TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    review_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


def upgrade() -> None:
    """Создать схему v1 (для пустой БД; существующая остаётся как есть)."""
    for stmt in filter(None, (s.strip() for s in V1_SCHEMA.split(";"))):
        op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
