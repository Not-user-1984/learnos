"""SQL-репозиторий повторений."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .tables import review_items


class ReviewRepository:
    """Элементы повторения по блокам."""

    def upsert(self, session: Session, **values) -> None:
        existing = session.execute(
            select(review_items).where(review_items.c.block_uid == values["block_uid"])
        ).first()
        if existing is None:
            session.execute(review_items.insert().values(**values))
        else:
            session.execute(
                update(review_items).where(review_items.c.block_uid == values["block_uid"]).values(**values)
            )

    def get(self, session: Session, block_uid: str) -> dict | None:
        row = session.execute(select(review_items).where(review_items.c.block_uid == block_uid)).first()
        return dict(row._mapping) if row else None

    def all(self, session: Session) -> list[dict]:
        rows = session.execute(select(review_items)).all()
        return [dict(r._mapping) for r in rows]
