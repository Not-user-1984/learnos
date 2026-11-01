"""«Проговорённое» знание: blocks.verified — блок вышел из сессии с фейнманом (R-18).

Отделяет урок (verified=true) от конспекта (verified=false): ядро продукта —
знание рождается через понимание, статус виден в API и переживает правки.

Revision ID: 0015_block_verified
Revises: 0014_conversation_active_agent
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_block_verified"
down_revision: str | None = "0014_conversation_active_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("blocks") as batch:
        batch.add_column(sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()))
    # уже существующие блоки из сессий — проговорённые
    op.execute("UPDATE blocks SET verified = 1 WHERE session_uid IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("blocks") as batch:
        batch.drop_column("verified")
