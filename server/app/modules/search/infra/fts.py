"""FTS5-репозиторий: blocks_fts и chapters_fts (создаются миграцией сырым SQL)."""

import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

_CHUNK = 8000  # чанк индексации главы: хвосты длинных глав находятся (R-19)

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


# разговорные слова, которые только мешают запросу (R-19)
_STOP_WORDS = {
    "и",
    "в",
    "на",
    "с",
    "по",
    "как",
    "что",
    "для",
    "это",
    "из",
    "у",
    "не",
    "к",
    "о",
    "от",
    "до",
    "при",
    "за",
    "же",
    "бы",
    "а",
    "но",
    "мне",
    "меня",
    "я",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "is",
    "how",
    "what",
    "why",
}


def fts_query(q: str) -> str:
    """FTS5-запрос, который прощает естественную речь (R-19).

    Слова через OR с ранжированием bm25 (раньше AND по точным токенам —
    «как работает pod» не находил ничего), стоп-слова выкидываем, корни ≥3
    символов — префиксные (`"контейнер"*` ловит «контейнеры»/«контейнера»).
    """
    words = [w for w in re.findall(r"[\w\u0400-\u04ff]+", q.lower()) if w and w not in _STOP_WORDS][:8]
    terms = [f'"{w}"*' if len(w) >= 3 else f'"{w}"' for w in words]
    return " OR ".join(terms) or '""'


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

    def delete_block(self, session: Session, uid: str) -> None:
        """Убрать блок из blocks_fts (событие BlockDeleted)."""
        session.execute(text("DELETE FROM blocks_fts WHERE block_uid = :uid"), {"uid": uid})

    def search_blocks(self, session: Session, q: str, limit: int) -> list[dict]:
        """Поиск по блокам: uid, title, summary, сниппет."""
        rows = (
            session.execute(
                text(
                    "SELECT block_uid, title, summary, snippet(blocks_fts, 3, '«', '»', '…', 12) AS snippet, "
                    "bm25(blocks_fts) AS rank "
                    "FROM blocks_fts WHERE blocks_fts MATCH :q "
                    "ORDER BY rank LIMIT :limit"
                ),
                {"q": fts_query(q), "limit": limit},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def search_chapters(self, session: Session, q: str, limit: int) -> list[dict]:
        """Поиск по главам: source_uid, chapter, title, сниппет.

        Глава индексируется чанками — схлопываем до одной строки на главу
        (первая = самый релевантный чанк по bm25).
        """
        rows = (
            session.execute(
                text(
                    "SELECT c.idx AS chapter, f.source_uid, f.title, "
                    "snippet(chapters_fts, 2, '«', '»', '…', 12) AS snippet, "
                    "bm25(chapters_fts) AS rank "
                    "FROM chapters_fts f JOIN chapters c ON c.id = f.chapter_id "
                    "WHERE chapters_fts MATCH :q ORDER BY rank"
                ),
                {"q": fts_query(q)},
            )
            .mappings()
            .all()
        )
        seen: set[tuple[str, int]] = set()
        out = []
        for r in rows:
            key = (r["source_uid"], r["chapter"])
            if key in seen:
                continue
            seen.add(key)
            out.append({k: r[k] for k in ("chapter", "source_uid", "title", "snippet")})
            if len(out) >= limit:
                break
        return out

    def delete_source(self, session: Session, source_uid: str) -> None:
        """Убрать главы источника из индекса (событие SourceDeleted)."""
        session.execute(text("DELETE FROM chapters_fts WHERE source_uid = :suid"), {"suid": source_uid})

    def reindex_chapters(self, session: Session, source_uid: str | None = None) -> None:
        """Пересобрать chapters_fts (тексты читаются с диска).

        Инкрементально (R-19): с source_uid — только его главы (событие
        SourceProcessed больше не устраивает полную пересборку всей библиотеки).
        Длинные главы индексируются чанками по ~8k — хвост не теряется.
        """
        if source_uid is not None:
            session.execute(text("DELETE FROM chapters_fts WHERE source_uid = :suid"), {"suid": source_uid})
        else:
            session.execute(text("DELETE FROM chapters_fts"))
        cond = "WHERE s.uid = :suid" if source_uid is not None else ""
        rows = (
            session.execute(
                text(
                    "SELECT c.id, c.path, c.title, c.summary, s.uid AS source_uid "
                    f"FROM chapters c JOIN sources s ON s.id = c.source_id {cond}"  # noqa: S608
                ),
                {"suid": source_uid},
            )
            .mappings()
            .all()
        )
        for r in rows:
            path = Path(r["path"])
            if not path.exists():
                continue
            body = f"{r['title']}\n{r['summary'] or ''}\n{path.read_text(encoding='utf-8')}"
            for i in range(0, min(len(body), 3 * _CHUNK), _CHUNK):
                session.execute(
                    text(
                        "INSERT INTO chapters_fts (chapter_id, source_uid, title, body) "
                        "VALUES (:cid, :suid, :title, :body)"
                    ),
                    {
                        "cid": r["id"],
                        "suid": r["source_uid"],
                        "title": r["title"],
                        "body": body[i : i + _CHUNK],
                    },
                )
