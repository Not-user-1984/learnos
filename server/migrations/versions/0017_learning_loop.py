"""Петля обучения (B-004): статус элемента курса + связь сессии с элементом.

Revision ID: 0017_learning_loop
Revises: 0016_concepts_assessments
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_learning_loop"
down_revision: str | None = "0016_concepts_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # курс — доска: у элемента явный статус todo|doing|read|done
    with op.batch_alter_table("course_items") as batch:
        batch.add_column(sa.Column("status", sa.Text, nullable=False, server_default="todo"))
    # сессия знает, какой элемент курса она закрывает
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("course_item_id", sa.Integer, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("course_item_id")
    with op.batch_alter_table("course_items") as batch:
        batch.drop_column("status")
