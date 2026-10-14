"""FTS5-репозиторий: blocks_fts и chapters_fts (создаются миграцией сырым SQL)."""

import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

FTS_TABLES_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
  block_uid UNINDEXED, title, summary, body, tags,
  tokenize='unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
  chapter_id UNINDEXED, source_uid UNINDEXED, title, body,
  tokenize='unicode61 remove_diacritics 2'
);
"""


def ensure_fts(session: Session) -> None:
    """Создать FTS-таблицы, если их нет (вызывается из миграции и на старте)."""
    for stmt in filter(None, (s.strip() for s in FTS_TABLES_SQL.split(";"))):
        session.execute(text(stmt))


def fts_query(q: str) -> str:
    """Безопасный FTS5-запрос: слова через AND, кавычки убраны."""
    words = [w for w in re.findall(r"[\w\u0400-\u04ff]+", q) if w]
    return " AND ".join(f'"{w}"' for w in words[:8]) or '""'


class FtsRepo:
    """Все операции с FTS-индексами идут через переданную сессию."""

    def upsert_block(
        self, session: Session, uid: str, title: str, summary: str, body: str, tags: str
    ) -> None:
        """Перезаписать строку блока в blocks_fts."""
        session.execute(text("DELETE FROM blocks_fts WHERE block_uid = :uid"), {"uid": uid})
        session.execute(
            text(
                "INSERT INTO blocks_fts (block_uid, title, summary, body, tags) "
                "VALUES (:uid, :title, :summary, :body, :tags)"
            ),
            {"uid": uid, "title": title, "summary": summary, "body": body, "tags": tags},
        )

    def search_blocks(self, session: Session, q: str, limit: int) -> list[dict]:
        """Поиск по блокам: uid, title, summary, сниппет."""
        rows = (
            session.execute(
                text(
                    "SELECT block_uid, title, summary, snippet(blocks_fts, 3, '«', '»', '…', 12) AS snippet "
                    "FROM blocks_fts WHERE blocks_fts MATCH :q LIMIT :limit"
                ),
                {"q": fts_query(q), "limit": limit},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def search_chapters(self, session: Session, q: str, limit: int) -> list[dict]:
        """Поиск по главам: source_uid, chapter, title, сниппет."""
        rows = (
            session.execute(
                text(
                    "SELECT c.idx AS chapter, f.source_uid, f.title, "
                    "snippet(chapters_fts, 2, '«', '»', '…', 12) AS snippet "
                    "FROM chapters_fts f JOIN chapters c ON c.id = f.chapter_id "
                    "WHERE chapters_fts MATCH :q LIMIT :limit"
                ),
                {"q": fts_query(q), "limit": limit},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def reindex_chapters(self, session: Session) -> None:
        """Пересобрать chapters_fts по всем главам (тексты читаются с диска)."""
        session.execute(text("DELETE FROM chapters_fts"))
        rows = (
            session.execute(
                text(
                    "SELECT c.id, c.path, c.title, s.uid AS source_uid "
                    "FROM chapters c JOIN sources s ON s.id = c.source_id"
                )
            )
            .mappings()
            .all()
        )
        for r in rows:
            path = Path(r["path"])
            if not path.exists():
                continue
            body = path.read_text(encoding="utf-8")[:60000]
            session.execute(
                text(
                    "INSERT INTO chapters_fts (chapter_id, source_uid, title, body) "
                    "VALUES (:cid, :suid, :title, :body)"
                ),
                {"cid": r["id"], "suid": r["source_uid"], "title": r["title"], "body": body},
            )
