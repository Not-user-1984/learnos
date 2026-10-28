"""Связь трейсов субагентов: parent_run_id в agent_runs. Модуль agent (T-035).

Revision ID: 0009_agent_runs_parent
Revises: 0008_chapter_navigation
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_agent_runs_parent"
down_revision: str | None = "0008_chapter_navigation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("parent_run_id", sa.Integer, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("parent_run_id")
