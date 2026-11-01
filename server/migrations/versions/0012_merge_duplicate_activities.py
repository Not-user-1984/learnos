"""Слияние дублей активностей: один курсор на (источник, курс) — R-11 аудита.

Повторные клики «Разбор/Сессия/Обсудить главу» плодили активности со статусом
active и курсором 1 — прогресс книги размазывался. Выжившая активность группы —
с максимальным курсором; разговоры и сессии дублей перевешиваются на неё.

Revision ID: 0012_merge_duplicate_activities
Revises: 0011_agent_runs_current_tool
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_merge_duplicate_activities"
down_revision: str | None = "0011_agent_runs_current_tool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, source_id, COALESCE(course_id, 0) AS cid, cursor_chapter "
            "FROM activities WHERE status = 'active' "
            "ORDER BY source_id, cid, cursor_chapter, id"
        )
    ).fetchall()
    groups: dict[tuple[int, int], list] = {}
    for r in rows:
        groups.setdefault((r.source_id, r.cid), []).append(r)

    bind = sa.bindparam("ids", expanding=True)
    for items in groups.values():
        if len(items) < 2:
            continue
        survivor = max(items, key=lambda r: (r.cursor_chapter, r.id))
        losers = [r.id for r in items if r.id != survivor.id]
        # разговоры и сессии дубля перевешиваем на выжившую активность группы
        for table in ("conversations", "sessions"):
            conn.execute(
                sa.text(
                    f"UPDATE {table} SET activity_id = :sid WHERE activity_id IN :ids"  # noqa: S608
                ).bindparams(bind),
                {"ids": losers, "sid": survivor.id},
            )
        conn.execute(
            sa.text("DELETE FROM activities WHERE id IN :ids").bindparams(bind),
            {"ids": losers},
        )


def downgrade() -> None:
    # слияние данных необратимо: дублей больше не существует
    pass
