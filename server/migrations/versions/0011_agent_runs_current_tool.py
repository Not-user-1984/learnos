"""Текущий инструмент живого запуска: current_tool в agent_runs (BUG-003).

Revision ID: 0011_agent_runs_current_tool
Revises: 0010_prompt_changes_kind
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_agent_runs_current_tool"
down_revision: str | None = "0010_prompt_changes_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("current_tool", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("current_tool")
