"""Модель знания: concepts (понятия блоков) и assessments (фейнман-пары) — T-051 Э5.

Понятия и проговоры становятся структурными данными: экзаменатор и reinforce
могут выбирать «самое слабое/созревшее» запросом, а не вычитывать transcript_json.

Revision ID: 0016_concepts_assessments
Revises: 0015_block_verified
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_concepts_assessments"
down_revision: str | None = "0015_block_verified"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uid", sa.Text, nullable=False, unique=True),
        sa.Column("block_uid", sa.Text, sa.ForeignKey("blocks.block_uid"), nullable=False),
        sa.Column("term", sa.Text, nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("ix_concepts_block", "concepts", ["block_uid"])
    op.create_table(
        "assessments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_uid", sa.Text, nullable=False),
        sa.Column("session_uid", sa.Text, nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text),
        sa.Column("verdict", sa.Text),
        sa.Column("quality", sa.Integer),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("ix_assessments_block", "assessments", ["block_uid"])


def downgrade() -> None:
    op.drop_index("ix_assessments_block", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index("ix_concepts_block", table_name="concepts")
    op.drop_table("concepts")
