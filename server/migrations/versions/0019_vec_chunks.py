"""Векторный индекс поиска (B-008): метаданные чанков и состояние модели.

Revision ID: 0019_vec_chunks
Revises: 0018_conversation_context_ref
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_vec_chunks"
down_revision: str | None = "0018_conversation_context_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vec_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_key", sa.Text, nullable=False),
        sa.Column("chunk_no", sa.Integer, nullable=False),
        sa.Column("text_hash", sa.Text, nullable=False),
        sa.Column("embedding_json", sa.Text, nullable=False),
    )
    op.create_index("ix_vec_chunks_item_key", "vec_chunks", ["item_key"])
    op.create_table(
        "vec_state",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )
    # vec0-таблица эмбеддингов создаётся при первом использовании (размерность модели)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vec_chunk_embeddings")
    op.drop_table("vec_state")
    op.drop_index("ix_vec_chunks_item_key", table_name="vec_chunks")
    op.drop_table("vec_chunks")
