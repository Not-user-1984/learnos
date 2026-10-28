"""Правки builtin-скиллов карточкой: kind/file в prompt_changes (T-037).

Revision ID: 0010_prompt_changes_kind
Revises: 0009_agent_runs_parent
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_prompt_changes_kind"
down_revision: str | None = "0009_agent_runs_parent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_changes") as batch:
        batch.add_column(sa.Column("kind", sa.Text, nullable=False, server_default="prompt"))
        batch.add_column(sa.Column("file", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_changes") as batch:
        batch.drop_column("file")
        batch.drop_column("kind")
