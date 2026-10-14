"""SQL-репозитории чата."""

from __future__ import annotations

import json

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import NotFound
from .tables import conversations, messages


class ConversationRepository:
    """Разговоры."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(conversations.insert().values(**values)).inserted_primary_key[0])

    def get(self, session: Session, uid: str) -> dict:
        row = session.execute(select(conversations).where(conversations.c.uid == uid)).first()
        if row is None:
            raise NotFound(f"разговор '{uid}' не найден")
        return _conv_dict(row)

    def list(
        self, session: Session, *, mode: str | None = None, q: str | None = None, limit: int = 50
    ) -> list[dict]:
        from sqlalchemy import func

        stmt = select(conversations)
        if mode:
            stmt = stmt.where(conversations.c.mode == mode)
        if q:
            stmt = stmt.where(func.lower(conversations.c.title).like(f"%{q.lower()}%"))
        rows = session.execute(stmt.order_by(conversations.c.updated_at.desc()).limit(limit)).all()
        return [_conv_dict(r) for r in rows]

    def update(self, session: Session, conv_id: int, **values) -> None:
        session.execute(update(conversations).where(conversations.c.id == conv_id).values(**values))

    def delete(self, session: Session, conv_id: int) -> None:
        session.execute(delete(messages).where(messages.c.conversation_id == conv_id))
        session.execute(delete(conversations).where(conversations.c.id == conv_id))


class MessageRepository:
    """Сообщения разговора."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(messages.insert().values(**values)).inserted_primary_key[0])

    def list(self, session: Session, conversation_id: int, limit: int = 200) -> list[dict]:
        rows = session.execute(
            select(messages).where(messages.c.conversation_id == conversation_id).order_by(messages.c.id)
        ).all()
        return [_msg_dict(r) for r in rows]

    def last_id(self, session: Session, conversation_id: int) -> int | None:
        from sqlalchemy import func

        return session.execute(
            select(func.max(messages.c.id)).where(messages.c.conversation_id == conversation_id)
        ).scalar_one_or_none()


def _conv_dict(r) -> dict:
    return {
        "id": r.id,
        "uid": r.uid,
        "title": r.title,
        "mode": r.mode,
        "activity_id": r.activity_id,
        "chapter_idx": r.chapter_idx,
        "focus_block_uid": r.focus_block_uid,
        "summary": r.summary,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _msg_dict(r) -> dict:
    return {
        "id": r.id,
        "conversation_id": r.conversation_id,
        "role": r.role,
        "content": r.content,
        "tool_calls": json.loads(r.tool_calls_json) if r.tool_calls_json else None,
        "tool_call_id": r.tool_call_id,
        "tool_name": r.tool_name,
        "cards": json.loads(r.cards_json or "[]"),
        "created_at": r.created_at,
    }
