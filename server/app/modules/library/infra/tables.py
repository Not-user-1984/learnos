"""Таблицы модуля library."""

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
)

from ....kernel.db import metadata

sources = Table(
    "sources",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("kind", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("author", Text),
    Column("url", Text),
    Column("local_path", Text),
    Column("status", Text, nullable=False, server_default="chosen"),
    Column("summary", Text),
    Column("meta_json", Text, nullable=False, server_default="{}"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

chapters = Table(
    "chapters",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("idx", Integer, nullable=False),
    Column("title", Text, nullable=False),
    Column("path", Text, nullable=False),
    Column("tokens_est", Integer),
    Column("summary", Text),
    Column("key_points_json", Text, nullable=False, server_default="[]"),
    Column("has_exercises", Integer, nullable=False, server_default="0"),
    UniqueConstraint("source_id", "idx", name="uq_chapters_source_idx"),
)
Index("ix_chapters_source_id", chapters.c.source_id)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", Text, nullable=False),
    Column("target", Text),
    Column("status", Text, nullable=False, server_default="queued"),
    Column("progress", Integer, nullable=False, server_default="0"),
    Column("total", Integer, nullable=False, server_default="0"),
    Column("message", Text),
    Column("error", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
