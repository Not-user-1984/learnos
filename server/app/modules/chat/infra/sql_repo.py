"""SQL-репозитории чата."""

from __future__ import annotations

import json

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import NotFound
from ..cards import ensure_card_ids
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

    def get_by_id(self, session: Session, conversation_id: int) -> dict:
        row = session.execute(select(conversations).where(conversations.c.id == conversation_id)).first()
        if row is None:
            raise NotFound(f"разговор {conversation_id} не найден")
        return _conv_dict(row)

    def list(
        self,
        session: Session,
        *,
        mode: str | None = None,
        q: str | None = None,
        activity_ids: list[int] | None = None,
        chapter: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Разговоры; activity_ids/chapter — фильтр «история по главе источника»."""
        from sqlalchemy import func

        stmt = select(conversations)
        if mode:
            stmt = stmt.where(conversations.c.mode == mode)
        if q:
            stmt = stmt.where(func.lower(conversations.c.title).like(f"%{q.lower()}%"))
        if activity_ids is not None:
            stmt = stmt.where(conversations.c.activity_id.in_(activity_ids or [-1]))
        if chapter is not None:
            stmt = stmt.where(conversations.c.chapter_idx == chapter)
        rows = session.execute(stmt.order_by(conversations.c.updated_at.desc()).limit(limit)).all()
        convs = [_conv_dict(r) for r in rows]
        ids = [c["id"] for c in convs]
        if ids:
            counts = dict(
                session.execute(
                    select(messages.c.conversation_id, func.count(messages.c.id))
                    .where(messages.c.conversation_id.in_(ids))
                    .group_by(messages.c.conversation_id)
                ).all()
            )
            for c in convs:
                c["messages_count"] = int(counts.get(c["id"], 0))
        return convs

    def set_active_agent(self, session: Session, conv_id: int, agent: str | None) -> None:
        """Сменить агента, ведущего разговор (handoff, T-050)."""
        session.execute(update(conversations).where(conversations.c.id == conv_id).values(active_agent=agent))

    def find_by_context_ref(self, session: Session, context_ref: str) -> dict | None:
        """Разговор по привязке к главе источника (split-view, B-006): свежий."""
        row = session.execute(
            select(conversations)
            .where(conversations.c.context_ref == context_ref)
            .order_by(conversations.c.id.desc())
        ).first()
        return _conv_dict(row) if row else None

    def update(self, session: Session, conv_id: int, **values) -> None:
        session.execute(update(conversations).where(conversations.c.id == conv_id).values(**values))

    def detach_activities(self, session: Session, activity_ids: list[int]) -> None:
        """Отвязать разговоры от активностей (история остаётся при удалении источника)."""
        if not activity_ids:
            return
        session.execute(
            update(conversations)
            .where(conversations.c.activity_id.in_(activity_ids))
            .values(activity_id=None)
        )

    def delete(self, session: Session, conv_id: int) -> None:
        # сессии-уроки остаются в истории, отвязанными от удалённого разговора
        from sqlalchemy import text

        session.execute(
            text("UPDATE sessions SET conversation_id=NULL WHERE conversation_id=:c"), {"c": conv_id}
        )
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

    def find_card(
        self, session: Session, conversation_id: int, card_id: str
    ) -> tuple[int | None, list[dict]]:
        """Сообщение и его карточки по card_id (B-003).

        Старым карточкам id генерируется тем же детерминированным правилом, что и
        при отдаче истории — resolve работает и по сообщениям до появления card_id.
        """
        for m in self.list(session, conversation_id):
            cards = ensure_card_ids(m["id"], m["cards"])
            if any(c.get("card_id") == card_id for c in cards):
                return m["id"], cards
        return None, []

    def update_cards(self, session: Session, message_id: int, cards: list[dict]) -> None:
        """Записать карточки сообщения (resolve/mark меняет status/choice, B-003)."""
        session.execute(
            update(messages)
            .where(messages.c.id == message_id)
            .values(cards_json=json.dumps(cards, ensure_ascii=False))
        )


def _conv_dict(r) -> dict:
    return {
        "id": r.id,
        "uid": r.uid,
        "title": r.title,
        "mode": r.mode,
        "active_agent": r.active_agent,
        "activity_id": r.activity_id,
        "chapter_idx": r.chapter_idx,
        "focus_block_uid": r.focus_block_uid,
        "context_ref": r.context_ref,
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
