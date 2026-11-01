"""Трасса шагов агентов: agent_steps — llm/tool/structured шаги запуска (R-24).

Агрегатов agent_runs было мало: токены structured-вызовов писались нулями,
шаги (инструмент, аргументы, статус, длительность) не сохранялись вовсе.

Revision ID: 0013_agent_steps
Revises: 0012_merge_duplicate_activities
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_agent_steps"
down_revision: str | None = "0012_merge_duplicate_activities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("args_json", sa.Text),
        sa.Column("result_summary", sa.Text),
        sa.Column("ok", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("ms", sa.Integer),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_steps_run_id", table_name="agent_steps")
    op.drop_table("agent_steps")
