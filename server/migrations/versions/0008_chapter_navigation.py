"""Навигация по книге: номер главы, границы страниц, секции level-2. Модуль library.

Revision ID: 0008_chapter_navigation
Revises: 0007_app_settings
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_chapter_navigation"
down_revision: str | None = "0007_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chapters") as batch:
        batch.add_column(sa.Column("number", sa.Integer, nullable=True))
        batch.add_column(sa.Column("start_page", sa.Integer, nullable=True))
        batch.add_column(sa.Column("end_page", sa.Integer, nullable=True))
        batch.add_column(sa.Column("sections_json", sa.Text, nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("chapters") as batch:
        batch.drop_column("sections_json")
        batch.drop_column("end_page")
        batch.drop_column("start_page")
        batch.drop_column("number")
