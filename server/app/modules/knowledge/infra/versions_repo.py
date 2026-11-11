"""Репозиторий версий блоков: block_versions (B-009: разрез sql_repo)."""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ....kernel.errors import NotFound
from .tables import block_versions


class BlockVersionsRepository:
    """История версий блока: снимки MD на каждую правку."""

    def add_version(
        self,
        session: Session,
        uid: str,
        version: int,
        content: str,
        reason: str | None,
        conversation_uid: str | None,
        created_at: str,
    ) -> None:
        """Сохранить предыдущую версию блока."""
        session.execute(
            insert(block_versions).values(
                block_uid=uid,
                version=version,
                content=content,
                reason=reason,
                conversation_uid=conversation_uid,
                created_at=created_at,
            )
        )

    def get_version(self, session: Session, uid: str, version: int) -> str:
        """Полный MD-контент указанной версии."""
        row = session.execute(
            select(block_versions.c.content).where(
                block_versions.c.block_uid == uid, block_versions.c.version == version
            )
        ).first()
        if row is None:
            raise NotFound(f"версия {version} блока '{uid}' не найдена")
        return row[0]

    def versions(self, session: Session, uid: str) -> list[dict]:
        """История версий (новые сверху)."""
        rows = session.execute(
            select(
                block_versions.c.version,
                block_versions.c.reason,
                block_versions.c.conversation_uid,
                block_versions.c.created_at,
                block_versions.c.content,
            )
            .where(block_versions.c.block_uid == uid)
            .order_by(block_versions.c.version.desc())
        ).all()
        return [
            {"version": r[0], "reason": r[1], "conversation_uid": r[2], "created_at": r[3], "size": len(r[4])}
            for r in rows
        ]
