"""Таблица трейсов запусков агентов (сквозной слой agent)."""

from sqlalchemy import Column, Integer, Table, Text

from ..kernel.db import metadata

agent_runs_table = Table(
    "agent_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("conversation_uid", Text),
    Column("status", Text, nullable=False),
    Column("steps", Integer, nullable=False, server_default="0"),
    Column("tool_calls", Integer, nullable=False, server_default="0"),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("duration_ms", Integer),
    Column("error", Text),
    Column("parent_run_id", Integer),  # трейс родителя: связывает субагентов с оркестратором
    Column("current_tool", Text),  # чем запуск занят прямо сейчас (label последнего инструмента)
    Column("created_at", Text, nullable=False),
)
