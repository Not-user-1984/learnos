"""Таблицы модуля learning: активности и сессии."""

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
)

from ....kernel.db import metadata

activities = Table(
    "activities",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("course_id", Integer, ForeignKey("courses.id")),
    Column("title", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),
    Column("cursor_chapter", Integer, nullable=False, server_default="1"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("conversation_id", Integer, ForeignKey("conversations.id")),
    Column("activity_id", Integer, ForeignKey("activities.id")),
    Column("course_id", Integer, ForeignKey("courses.id")),
    Column("chapter_idx", Integer),
    Column("idx", Integer, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),
    Column("state", Text, nullable=False, server_default="theory"),
    Column("config_json", Text, nullable=False, server_default="{}"),
    Column("started_at", Text, nullable=False),
    Column("ended_at", Text),
    Column("transcript_json", Text, nullable=False, server_default="[]"),
)
Index("ix_sessions_conversation", sessions.c.conversation_id)
