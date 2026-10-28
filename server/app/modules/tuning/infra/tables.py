"""Таблицы tuning: стадия правок промптов и кастомные агенты."""

from sqlalchemy import Column, Integer, Table, Text

from ....kernel.db import metadata

prompt_changes = Table(
    "prompt_changes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent", Text, nullable=False),  # prompt: имя агента; skill: имя builtin-скилла
    Column("summary", Text, nullable=False),
    Column("old_content", Text, nullable=False),
    Column("new_content", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),  # pending|applied|rejected
    Column("kind", Text, nullable=False, server_default="prompt"),  # prompt|skill
    Column("file", Text),  # skill: run.py | SKILL.md
    Column("conversation_uid", Text),
    Column("created_at", Text, nullable=False),
)

custom_agents = Table(
    "custom_agents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False, unique=True),
    Column("description", Text, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("tools_json", Text, nullable=False, server_default="[]"),
    Column("model_role", Text, nullable=False, server_default="chat"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
