"""Таблица повторений review_items (этап 8 C).

Revision ID: 0003_review
Revises: 0002_v2
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_review"
down_revision: str | None = "0002_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_uid", sa.Text, nullable=False, unique=True),
        sa.Column("ease", sa.Integer, nullable=False, server_default="25"),
        sa.Column("interval_days", sa.Integer, nullable=False, server_default="1"),
        sa.Column("due_at", sa.Text, nullable=False),
        sa.Column("last_quality", sa.Integer),
        sa.Column("reps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("review_items")
