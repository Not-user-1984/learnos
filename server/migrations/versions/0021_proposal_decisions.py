"""Решения по предложениям агентов (B-010).

Revision ID: 0021_proposal_decisions
Revises: 0020_schedules
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_proposal_decisions"
down_revision: str | None = "0020_schedules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_decisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("ref", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("decided_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("proposal_decisions")
