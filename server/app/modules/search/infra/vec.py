"""Векторный индекс (B-008): метаданные чанков + эмбеддинги + KNN.

Эмбеддинги хранятся и в vec0-таблице (sqlite-vec, прод — быстрый KNN), и в
embedding_json самой строки чанка: без расширения (мак-дев без loadable
extensions) KNN считается наивным косинусом по Python — медленно, но честно,
поиск не деградирует молча.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import TYPE_CHECKING

from sqlalchemy import Column, Index, Integer, Table, Text, delete, select, text

from ....kernel.db import metadata

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger("learnos.search.vec")

VEC_TABLE = "vec_chunk_embeddings"

vec_chunks = Table(
    "vec_chunks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # "blk_…" для блоков, "src_…:N" для глав
    Column("item_key", Text, nullable=False),
    Column("chunk_no", Integer, nullable=False),
    # sha256 текста чанка: инкрементальный reindex не пересчитывает совпадающее
    Column("text_hash", Text, nullable=False),
    # копия эмбеддинга для fallback-KNN без sqlite-vec
    Column("embedding_json", Text, nullable=False),
)
Index("ix_vec_chunks_item_key", vec_chunks.c.item_key)

vec_state = Table(
    "vec_state",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
)


def text_hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - dot / (na * nb)  # расстояние: меньше — ближе


class VecRepo:
    """Чанки и KNN-поиск по эмбеддингам: vec0 на проде, Python-cosine без расширения."""

    def vec_available(self, session: Session) -> bool:
        """Расширение sqlite-vec загружено в этом соединении?"""
        try:
            session.execute(text("SELECT vec_version()"))
            return True
        except Exception:  # noqa: BLE001 — нет расширения → Python-fallback
            return False

    def ensure(self, session: Session, dim: int, model: str) -> bool:
        """Создать/пересобрать vec0 под размерность модели (смена — полный пересбор)."""
        state = dict(session.execute(select(vec_state)).all())
        if state.get("dim") == str(dim) and state.get("model") == model:
            return self._ensure_vec0(session, dim)
        if state:
            log.info("vec: смена модели (%s → %s) — полный пересбор индекса", state.get("model"), model)
            session.execute(text(f"DROP TABLE IF EXISTS {VEC_TABLE}"))
            session.execute(delete(vec_chunks))
            session.execute(delete(vec_state))
        session.execute(vec_state.insert().values(key="dim", value=str(dim)))
        session.execute(vec_state.insert().values(key="model", value=model))
        return self._ensure_vec0(session, dim)

    def _ensure_vec0(self, session: Session, dim: int) -> bool:
        if not self.vec_available(session):
            return False
        session.execute(
            text(f"CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE} USING vec0(embedding float[{dim}])")
        )
        return True

    def item_hash(self, session: Session, item_key: str) -> str | None:
        """Хэш последнего чанка элемента (по нему пропускаем переиндексацию)."""
        row = session.execute(
            select(vec_chunks.c.text_hash)
            .where(vec_chunks.c.item_key == item_key)
            .order_by(vec_chunks.c.chunk_no.desc())
            .limit(1)
        ).first()
        return row[0] if row else None

    def upsert_item(self, session: Session, item_key: str, chunks: list[tuple[str, list[float]]]) -> None:
        """Заменить векторы элемента: [(текст_чанка, эмбеддинг)]."""
        self.delete_item(session, item_key)
        use_vec0 = self._ensure_vec0(session, len(chunks[0][1])) if chunks else False
        for chunk_no, (chunk_text, embedding) in enumerate(chunks):
            row_id = session.execute(
                vec_chunks.insert().values(
                    item_key=item_key,
                    chunk_no=chunk_no,
                    text_hash=text_hash(chunk_text),
                    embedding_json=json.dumps(embedding),
                )
            ).inserted_primary_key[0]
            if use_vec0:
                session.execute(
                    text(f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (:rowid, :embedding)"),
                    {"rowid": row_id, "embedding": json.dumps(embedding)},
                )

    def delete_item(self, session: Session, item_key: str) -> None:
        rows = session.execute(select(vec_chunks.c.id).where(vec_chunks.c.item_key == item_key)).all()
        if not rows:
            return
        session.execute(delete(vec_chunks).where(vec_chunks.c.item_key == item_key))
        if self.vec_available(session):
            ids = ",".join(str(r[0]) for r in rows)
            session.execute(text(f"DELETE FROM {VEC_TABLE} WHERE rowid IN ({ids})"))

    def knn(self, session: Session, embedding: list[float], limit: int = 20) -> list[dict]:
        """Ближайшие чанки: item_key, chunk_no, distance."""
        if self.vec_available(session):
            try:
                return self._knn_vec0(session, embedding, limit)
            except Exception:  # noqa: BLE001 — расширение есть, но ответило ошибкой
                log.warning("vec0 KNN упал — fallback на Python-cosine", exc_info=True)
        return self._knn_python(session, embedding, limit)

    def _knn_vec0(self, session: Session, embedding: list[float], limit: int) -> list[dict]:
        rows = (
            session.execute(
                text(
                    f"SELECT rowid, distance FROM {VEC_TABLE} "
                    "WHERE embedding MATCH :embedding AND k = :k ORDER BY distance"
                ),
                {"embedding": json.dumps(embedding), "k": limit},
            )
            .mappings()
            .all()
        )
        if not rows:
            return []
        by_id = dict(
            session.execute(select(vec_chunks.c.id, vec_chunks.c.item_key, vec_chunks.c.chunk_no)).all()
        )
        return [
            {"item_key": by_id[r["rowid"]][0], "chunk_no": by_id[r["rowid"]][1], "distance": r["distance"]}
            for r in rows
            if r["rowid"] in by_id
        ]

    def _knn_python(self, session: Session, embedding: list[float], limit: int) -> list[dict]:
        rows = session.execute(
            select(vec_chunks.c.item_key, vec_chunks.c.chunk_no, vec_chunks.c.embedding_json)
        ).all()
        scored = []
        for item_key, chunk_no, blob in rows:
            vec = json.loads(blob)
            scored.append({"item_key": item_key, "chunk_no": chunk_no, "distance": _cosine(embedding, vec)})
        scored.sort(key=lambda r: r["distance"])
        return scored[:limit]

    def count_items(self, session: Session) -> int:
        return len(session.execute(select(vec_chunks.c.item_key).distinct()).all())

    def state(self, session: Session) -> dict:
        return dict(session.execute(select(vec_state)).all())
