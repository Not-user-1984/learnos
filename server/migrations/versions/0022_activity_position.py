"""Место чтения книги в активности (B-013): глава + страница PDF.

Revision ID: 0022_activity_position
Revises: 0021_proposal_decisions
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_activity_position"
down_revision: str | None = "0021_proposal_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # где читатель остановился: position_chapter/position_page ≠ курсор прогресса
    with op.batch_alter_table("activities") as batch:
        batch.add_column(sa.Column("position_chapter", sa.Integer, nullable=True))
        batch.add_column(sa.Column("position_page", sa.Integer, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activities") as batch:
        batch.drop_column("position_page")
        batch.drop_column("position_chapter")
