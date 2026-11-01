"""Таблицы чата: разговоры и сообщения."""

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
)

from ....kernel.db import metadata

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("title", Text, nullable=False, server_default="Новый разговор"),
    Column("mode", Text, nullable=False, server_default="free"),
    # handoff (T-050 Э4): агент, который ведёт разговор; NULL — по mode (легаси)
    Column("active_agent", Text, nullable=True),
    Column("activity_id", Integer, ForeignKey("activities.id")),
    Column("chapter_idx", Integer),
    Column("focus_block_uid", Text),
    Column("summary", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conversation_id", Integer, ForeignKey("conversations.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False, server_default=""),
    Column("tool_calls_json", Text),
    Column("tool_call_id", Text),
    Column("tool_name", Text),
    Column("cards_json", Text, server_default="[]"),
    Column("created_at", Text, nullable=False),
)
Index("ix_messages_conversation", messages.c.conversation_id, messages.c.id)
