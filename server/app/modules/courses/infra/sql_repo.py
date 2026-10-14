"""SQL-репозиторий курсов."""

from __future__ import annotations

import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import NotFound
from .tables import course_items, courses


class CourseRepository:
    """Курсы и элементы."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(courses.insert().values(**values)).inserted_primary_key[0])

    def get(self, session: Session, ref: str | int) -> dict:
        row = session.execute(select(courses).where(_cond(ref))).first()
        if row is None:
            raise NotFound(f"курс '{ref}' не найден")
        return _course_dict(row)

    def list(self, session: Session) -> list[dict]:
        rows = session.execute(select(courses).order_by(courses.c.id.desc())).all()
        return [_course_dict(r) for r in rows]

    def update(self, session: Session, course_id: int, **values) -> None:
        session.execute(update(courses).where(courses.c.id == course_id).values(**values))

    def delete(self, session: Session, course_id: int) -> None:
        session.execute(delete(course_items).where(course_items.c.course_id == course_id))
        session.execute(delete(courses).where(courses.c.id == course_id))

    def add_item(self, session: Session, course_id: int, position: int, **values) -> int:
        return int(
            session.execute(
                course_items.insert().values(course_id=course_id, position=position, **values)
            ).inserted_primary_key[0]
        )

    def items(self, session: Session, course_id: int) -> list[dict]:
        rows = session.execute(
            select(course_items)
            .where(course_items.c.course_id == course_id)
            .order_by(course_items.c.position)
        ).all()
        return [_item_dict(r) for r in rows]

    def item(self, session: Session, item_id: int) -> dict:
        row = session.execute(select(course_items).where(course_items.c.id == item_id)).first()
        if row is None:
            raise NotFound(f"элемент курса {item_id} не найден")
        return _item_dict(row)

    def remove_item(self, session: Session, item_id: int) -> None:
        session.execute(delete(course_items).where(course_items.c.id == item_id))

    def count_items(self, session: Session, course_id: int) -> int:
        return int(
            session.execute(select(func.count()).where(course_items.c.course_id == course_id)).scalar_one()
        )

    def reorder(self, session: Session, course_id: int, item_ids: list[int]) -> None:
        for pos, item_id in enumerate(item_ids, 1):
            session.execute(
                update(course_items)
                .where(course_items.c.id == item_id, course_items.c.course_id == course_id)
                .values(position=pos)
            )


def _cond(ref):
    return courses.c.uid == ref if isinstance(ref, str) and not ref.isdigit() else courses.c.id == int(ref)


def _course_dict(r) -> dict:
    return {
        "id": r.id,
        "uid": r.uid,
        "title": r.title,
        "topic": r.topic,
        "description": r.description,
        "category_path": r.category_path,
        "status": r.status,
        "plan": json.loads(r.plan_json or "{}"),
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _item_dict(r) -> dict:
    return {
        "id": r.id,
        "course_id": r.course_id,
        "position": r.position,
        "item_type": r.item_type,
        "source_id": r.source_id,
        "chapter_idx": r.chapter_idx,
        "block_uid": r.block_uid,
        "note": r.note,
    }
