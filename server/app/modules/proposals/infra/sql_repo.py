"""Репозиторий решений по предложениям (B-010)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .tables import proposal_decisions


class DecisionRepository:
    """Решения живут в БД: файлы задач в /repo не всегда доступны на запись."""

    def decide(self, session: Session, kind: str, ref: str, decision: str, now: str) -> None:
        import sqlalchemy as sa

        session.execute(
            sa.delete(proposal_decisions).where(
                proposal_decisions.c.kind == kind, proposal_decisions.c.ref == ref
            )
        )
        session.execute(
            proposal_decisions.insert().values(kind=kind, ref=ref, decision=decision, decided_at=now)
        )

    def all(self, session: Session) -> dict[tuple[str, str], str]:
        rows = session.execute(select(proposal_decisions)).all()
        return {(r[1], r[2]): r[3] for r in rows}
