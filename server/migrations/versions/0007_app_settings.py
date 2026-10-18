"""Таблица app_settings: ключ-значение настроек из UI (поиск/прокси). Модуль research.

Revision ID: 0007_app_settings
Revises: 0006_external_mcp
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_app_settings"
down_revision: str | None = "0006_external_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_at", sa.Text, nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
