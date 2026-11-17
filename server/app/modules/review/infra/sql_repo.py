"""SQL-репозиторий повторений."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .tables import review_card_items, review_items


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

    def delete(self, session: Session, block_uid: str) -> None:
        """Блоковый элемент (блок перешёл на карточки или удалён)."""
        session.execute(review_items.delete().where(review_items.c.block_uid == block_uid))

    # --- карточки-суть (B-014): SM-2 на каждую ---

    def upsert_card(self, session: Session, **values) -> None:
        existing = session.execute(
            select(review_card_items).where(
                review_card_items.c.block_uid == values["block_uid"],
                review_card_items.c.card_id == values["card_id"],
            )
        ).first()
        if existing is None:
            session.execute(review_card_items.insert().values(**values))
        else:
            session.execute(
                update(review_card_items)
                .where(
                    review_card_items.c.block_uid == values["block_uid"],
                    review_card_items.c.card_id == values["card_id"],
                )
                .values(**values)
            )

    def get_card(self, session: Session, block_uid: str, card_id: str) -> dict | None:
        row = session.execute(
            select(review_card_items).where(
                review_card_items.c.block_uid == block_uid, review_card_items.c.card_id == card_id
            )
        ).first()
        return dict(row._mapping) if row else None

    def all_cards(self, session: Session) -> list[dict]:
        rows = session.execute(select(review_card_items)).all()
        return [dict(r._mapping) for r in rows]

    def delete_for_block(self, session: Session, block_uid: str) -> None:
        """Все карточные элементы блока (блок удалён / карточки убраны)."""
        session.execute(review_card_items.delete().where(review_card_items.c.block_uid == block_uid))

    def delete_card_items_except(self, session: Session, block_uid: str, keep_ids: list[str]) -> None:
        """Карточные элементы исчезнувших карточек (fix ревью B-014)."""
        stmt = review_card_items.delete().where(review_card_items.c.block_uid == block_uid)
        if keep_ids:
            stmt = stmt.where(review_card_items.c.card_id.not_in(keep_ids))
        session.execute(stmt)
