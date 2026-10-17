"""Таблица изменений промптов prompt_changes (модуль tuning).

Revision ID: 0004_tuning
Revises: 0003_review
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tuning"
down_revision: str | None = "0003_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_changes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("old_content", sa.Text, nullable=False),
        sa.Column("new_content", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("conversation_uid", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("prompt_changes")
