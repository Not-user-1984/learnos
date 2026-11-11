"""Расписания планировщика (B-010).

Revision ID: 0020_schedules
Revises: 0019_vec_chunks
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_schedules"
down_revision: str | None = "0019_vec_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("cron", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("args_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.Text),
        sa.Column("last_status", sa.Text, nullable=False, server_default="never"),
    )


def downgrade() -> None:
    op.drop_table("schedules")
