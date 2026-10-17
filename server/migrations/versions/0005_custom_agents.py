"""Таблица кастомных агентов custom_agents (модуль tuning).

Revision ID: 0005_custom_agents
Revises: 0004_tuning
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_custom_agents"
down_revision: str | None = "0004_tuning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_agents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("tools_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("model_role", sa.Text, nullable=False, server_default="chat"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("custom_agents")
