"""Таблица расписаний (B-010)."""

from sqlalchemy import Column, Integer, Table, Text

from ....kernel.db import metadata

schedules = Table(
    "schedules",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False, unique=True),
    Column("cron", Text, nullable=False),
    # job:review_digest | agent:auditor | agent:repo_scout
    Column("action", Text, nullable=False),
    Column("args_json", Text, nullable=False, server_default="{}"),
    Column("enabled", Integer, nullable=False, server_default="0"),
    Column("last_run_at", Text),
    Column("last_status", Text, nullable=False, server_default="never"),
)
