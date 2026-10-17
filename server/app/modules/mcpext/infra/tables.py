"""Таблицы mcpext: сторонние MCP-подключения."""

from sqlalchemy import Column, Integer, Table, Text

from ....kernel.db import metadata

external_mcps = Table(
    "external_mcps",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False, unique=True),
    Column("url", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("headers_json", Text, nullable=False, server_default="{}"),
    Column("tools_json", Text, nullable=False, server_default="[]"),  # кэш list_tools
    Column("enabled", Integer, nullable=False, server_default="1"),
    Column("status", Text, nullable=False, server_default="unchecked"),  # ok|error|unchecked
    Column("last_error", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
