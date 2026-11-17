"""Карточки-суть (B-014): cards в индексе блоков + SM-2 на карточку.

Revision ID: 0023_cards
Revises: 0022_activity_position
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_cards"
down_revision: str | None = "0022_activity_position"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("blocks") as batch:
        batch.add_column(sa.Column("cards_json", sa.Text, nullable=False, server_default="[]"))
    op.create_table(
        "review_card_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_uid", sa.Text, nullable=False),
        sa.Column("card_id", sa.Text, nullable=False),
        sa.Column("ease", sa.Integer, nullable=False, server_default="25"),
        sa.Column("interval_days", sa.Integer, nullable=False, server_default="1"),
        sa.Column("due_at", sa.Text, nullable=False),
        sa.Column("last_quality", sa.Integer),
        sa.Column("reps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("block_uid", "card_id", name="uq_review_card_item"),
    )


def downgrade() -> None:
    op.drop_table("review_card_items")
    with op.batch_alter_table("blocks") as batch:
        batch.drop_column("cards_json")
