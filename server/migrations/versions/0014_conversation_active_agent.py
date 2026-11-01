"""Handoff в разговорах: conversations.active_agent (T-050 Э4, R-13 аудита).

Интент первого сообщения передаёт разговор специалисту (review→quick_reviewer,
session→session_tutor), инструмент handoff — смена ведущего агента по ходу.
NULL — разговор ведётся по mode, как раньше (легаси-режимы).

Revision ID: 0014_conversation_active_agent
Revises: 0013_agent_steps
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_conversation_active_agent"
down_revision: str | None = "0013_agent_steps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("active_agent", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("active_agent")
