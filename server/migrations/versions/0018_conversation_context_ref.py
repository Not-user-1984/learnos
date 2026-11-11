"""Разговор, привязанный к главе источника (B-006): split-view «читаю и обсуждаю».

Revision ID: 0018_conversation_context_ref
Revises: 0017_learning_loop
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_conversation_context_ref"
down_revision: str | None = "0017_learning_loop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # "source_uid:chapter_idx" — get-or-create разговора главы
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("context_ref", sa.Text, nullable=True))
    op.create_index("ix_conversations_context_ref", "conversations", ["context_ref"])


def downgrade() -> None:
    op.drop_index("ix_conversations_context_ref", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("context_ref")
