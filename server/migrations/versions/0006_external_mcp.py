"""Таблица внешних MCP-подключений external_mcps (модуль mcpext).

Revision ID: 0006_external_mcp
Revises: 0005_custom_agents
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_external_mcp"
down_revision: str | None = "0005_custom_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_mcps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("headers_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("tools_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.Text, nullable=False, server_default="unchecked"),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("external_mcps")
