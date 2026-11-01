"""Таблица трейсов запусков агентов (сквозной слой agent)."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Table, Text

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
agent_steps_table = Table(
    "agent_steps",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", Integer, ForeignKey("agent_runs.id"), nullable=False),
    Column("idx", Integer, nullable=False),
    Column("kind", Text, nullable=False),  # llm | tool | structured
    Column("name", Text, nullable=False),
    Column("args_json", Text),
    Column("result_summary", Text),
    Column("ok", Boolean, nullable=False, default=True),
    Column("ms", Integer),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("created_at", Text, nullable=False),
)
