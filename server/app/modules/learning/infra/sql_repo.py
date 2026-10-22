"""SQL-репозитории learning: сессии и активности."""

from __future__ import annotations

import json

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import NotFound
from .tables import activities, sessions


class SessionRepository:
    """Сессии обучения."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(sessions.insert().values(**values)).inserted_primary_key[0])

    def get_by_id(self, session: Session, session_id: int) -> dict:
        row = session.execute(select(sessions).where(sessions.c.id == session_id)).first()
        if row is None:
            raise NotFound(f"сессия {session_id} не найдена")
        return _session_dict(row)

    def find_by_id(self, session: Session, session_id: int) -> dict | None:
        try:
            return self.get_by_id(session, session_id)
        except NotFound:
            return None

    def get_by_uid(self, session: Session, uid: str) -> dict:
        row = session.execute(select(sessions).where(sessions.c.uid == uid)).first()
        if row is None:
            raise NotFound(f"сессия {uid} не найдена")
        return _session_dict(row)

    def find_by_conversation(self, session: Session, conversation_id: int) -> dict | None:
        row = session.execute(
            select(sessions)
            .where(sessions.c.conversation_id == conversation_id, sessions.c.status == "active")
            .order_by(sessions.c.id.desc())
        ).first()
        return _session_dict(row) if row else None

    def count_for_course(self, session: Session, course_id: int) -> int:
        return int(
            session.execute(select(func.count()).where(sessions.c.course_id == course_id)).scalar_one()
        )

    def count_for_activity(self, session: Session, activity_id: int) -> int:
        """Число сессий активности (для запрета удаления активности)."""
        return int(
            session.execute(select(func.count()).where(sessions.c.activity_id == activity_id)).scalar_one()
        )

    def delete(self, session: Session, session_id: int) -> None:
        """Удалить сессию (блоки по ней должны быть удалены ранее — иначе запрет)."""
        session.execute(sessions.delete().where(sessions.c.id == session_id))

    def update(self, session: Session, session_id: int, **values) -> None:
        session.execute(update(sessions).where(sessions.c.id == session_id).values(**values))

    def detach_activities(self, session: Session, activity_ids: list[int]) -> None:
        """Отвязать сессии от активностей (при удалении источника история сессий остаётся)."""
        if not activity_ids:
            return
        session.execute(
            update(sessions).where(sessions.c.activity_id.in_(activity_ids)).values(activity_id=None)
        )


class ActivityRepository:
    """Активности «идём по источнику»."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(activities.insert().values(**values)).inserted_primary_key[0])

    def get(self, session: Session, ref: str | int) -> dict:
        cond = (
            activities.c.uid == ref
            if isinstance(ref, str) and not ref.isdigit()
            else activities.c.id == int(ref)
        )
        row = session.execute(select(activities).where(cond)).first()
        if row is None:
            raise NotFound(f"активность '{ref}' не найдена")
        return _activity_dict(row)

    def find(self, session: Session, ref: str | int) -> dict | None:
        try:
            return self.get(session, ref)
        except NotFound:
            return None

    def list(self, session: Session, *, status: str | None = None) -> list[dict]:
        stmt = select(activities)
        if status:
            stmt = stmt.where(activities.c.status == status)
        rows = session.execute(stmt.order_by(activities.c.updated_at.desc())).all()
        return [_activity_dict(r) for r in rows]

    def ids_for_source(self, session: Session, source_id: int) -> list[int]:
        """id активностей источника (фильтр разговоров по главе)."""
        rows = session.execute(select(activities.c.id).where(activities.c.source_id == source_id)).all()
        return [r[0] for r in rows]

    def update(self, session: Session, activity_id: int, **values) -> None:
        session.execute(update(activities).where(activities.c.id == activity_id).values(**values))

    def delete_ids(self, session: Session, activity_ids: list[int]) -> None:
        """Удалить активности (сессии и разговоры должны быть отвязаны/удалены ранее)."""
        if not activity_ids:
            return
        session.execute(activities.delete().where(activities.c.id.in_(activity_ids)))


def _session_dict(r) -> dict:
    return {
        "id": r.id,
        "uid": r.uid,
        "conversation_id": r.conversation_id,
        "activity_id": r.activity_id,
        "course_id": r.course_id,
        "chapter_idx": r.chapter_idx,
        "idx": r.idx,
        "status": r.status,
        "state": r.state,
        "config": json.loads(r.config_json or "{}"),
        "started_at": r.started_at,
        "ended_at": r.ended_at,
        "transcript": json.loads(r.transcript_json or "[]"),
    }


def _activity_dict(r) -> dict:
    return {
        "id": r.id,
        "uid": r.uid,
        "source_id": r.source_id,
        "course_id": r.course_id,
        "title": r.title,
        "status": r.status,
        "cursor_chapter": r.cursor_chapter,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }
