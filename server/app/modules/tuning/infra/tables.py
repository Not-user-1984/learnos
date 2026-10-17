"""Таблица изменений промптов (стадия → approve/reject)."""

from sqlalchemy import Column, Integer, Table, Text

from ....kernel.db import metadata

prompt_changes = Table(
    "prompt_changes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("old_content", Text, nullable=False),
    Column("new_content", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),  # pending|applied|rejected
    Column("conversation_uid", Text),
    Column("created_at", Text, nullable=False),
)
