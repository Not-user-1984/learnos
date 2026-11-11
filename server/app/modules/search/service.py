"""Сервис поиска: FTS5 по блокам и главам + векторы (гибрид, B-008)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import LLMError

if TYPE_CHECKING:
    from ...llm.router import ModelRouter
    from .infra.fts import FtsRepo
    from .infra.vec import VecRepo

log = logging.getLogger("learnos.search")

# чанки индексации: ~1000 символов по предложениям (B-008)
CHUNK_TARGET_CHARS = 1000
# RRF-константа слияния ранков FTS и векторов
RRF_K = 60


def chunk_text(text: str, target: int = CHUNK_TARGET_CHARS) -> list[str]:
    """Разбить текст на чанки ~target символов по предложениям."""
    sentences = re.split(r"(?<=[.!?…\n])\s+", text.strip())
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if buf and len(buf) + len(sentence) > target:
            chunks.append(buf.strip())
            buf = sentence
        else:
            buf += " " + sentence if buf else sentence
        while len(buf) > target * 2:  # предложение без точек длиннее двух чанков
            chunks.append(buf[:target])
            buf = buf[target:]
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [text[:target]]


def rrf_fuse(rankings: list[list[str]], limit: int) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: элементы сходятся по 1/(RRF_K+rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])[:limit]


class SearchService:
    """Поиск с областью blocks|chapters|all. FTS обновляется по событиям,
    векторы — через роль embed (hybrid = RRF, B-008); без роли — чистый FTS."""

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        fts: FtsRepo,
        knowledge,
        vec: VecRepo | None = None,
        router: ModelRouter | None = None,
    ) -> None:
        self._uow = uow
        self._fts = fts
        self._kb = knowledge
        self._vec = vec
        self._router = router

    # --- поиск ---

    def search(self, q: str, scope: str = "all", limit: int = 10, mode: str = "hybrid") -> dict:
        """Поиск: mode hybrid (RRF FTS+векторы) | fts | vector."""
        if scope not in {"blocks", "chapters", "all"}:
            scope = "all"
        if mode not in {"hybrid", "fts", "vector"}:
            mode = "hybrid"

        fts_out: dict[str, Any] = {"query": q, "scope": scope}
        if mode in {"hybrid", "fts"}:
            with self._uow() as uow:
                if scope in {"blocks", "all"}:
                    fts_out["blocks"] = self._fts.search_blocks(uow.session, q, limit)
                if scope in {"chapters", "all"}:
                    fts_out["chunks"] = self._fts.search_chapters(uow.session, q, limit)
        if mode == "fts":
            return fts_out

        vector = self._vector_search(q, limit * 3)
        if mode == "vector":
            blocks = [
                {"block_uid": r["item_key"], "title": r["title"], "distance": r["distance"]}
                for r in vector
                if r["item_key"].startswith("blk_")
            ][:limit]
            chunks = []
            for r in vector:
                if not r["item_key"].startswith("blk_"):
                    src_uid, _, ch = r["item_key"].rpartition(":")
                    chunks.append(
                        {"source_uid": src_uid, "chapter": ch, "title": r["title"], "distance": r["distance"]}
                    )
            return {"query": q, "mode": "vector", "blocks": blocks, "chunks": chunks[:limit]}

        return self._hybrid(q, scope, limit, fts_out, vector)

    def _hybrid(self, q: str, scope: str, limit: int, fts_out: dict, vector: list[dict]) -> dict:
        fts_blocks = [h["block_uid"] for h in fts_out.get("blocks", [])]
        fts_chunks = [f"{h['source_uid']}:{h['chapter']}" for h in fts_out.get("chunks", [])]
        vec_by_key = {r["item_key"]: r for r in vector}

        blocks_out, chunks_out = [], []
        if scope in {"blocks", "all"}:
            vec_blocks = [k for k in vec_by_key if k.startswith("blk_")]
            for uid, score in rrf_fuse([fts_blocks, vec_blocks], limit):
                hit = next((h for h in fts_out.get("blocks", []) if h["block_uid"] == uid), None)
                vec = vec_by_key.get(uid)
                blocks_out.append(
                    {
                        "block_uid": uid,
                        "title": hit["title"] if hit else (vec["title"] if vec else uid),
                        "summary": hit.get("summary") if hit else None,
                        "snippet": (hit.get("snippet") if hit else None) or (vec["title"] if vec else ""),
                        "score": round(score, 5),
                        "matched_by": "fts+vector" if hit and vec else ("vector" if vec else "fts"),
                    }
                )
        if scope in {"chapters", "all"}:
            vec_chunks = [k for k in vec_by_key if not k.startswith("blk_")]
            for key, score in rrf_fuse([fts_chunks, vec_chunks], limit):
                hit = next(
                    (h for h in fts_out.get("chunks", []) if f"{h['source_uid']}:{h['chapter']}" == key), None
                )
                vec = vec_by_key.get(key)
                src_uid, _, ch = key.rpartition(":")
                chunks_out.append(
                    {
                        "source_uid": src_uid,
                        "chapter": int(ch) if ch.isdigit() else ch,
                        "title": hit["title"] if hit else (vec["title"] if vec else key),
                        "snippet": (hit.get("snippet") if hit else None) or "",
                        "score": round(score, 5),
                        "matched_by": "fts+vector" if hit and vec else ("vector" if vec else "fts"),
                    }
                )
        return {"query": q, "scope": scope, "mode": "hybrid", "blocks": blocks_out, "chunks": chunks_out}

    # --- векторный слой ---

    def embed_ready(self) -> bool:
        """Роль embed настроена (иначе поиск деградирует в чистый FTS)."""
        return self._resolve_embed()[0] is not None

    def _resolve_embed(self):
        if self._router is None:
            return None, None
        try:
            provider, model, _params = self._router.resolve("embed")
            return provider, model
        except LLMError:
            return None, None

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        provider, model = self._resolve_embed()
        if provider is None:
            return None
        try:
            return run_coro_sync(provider.embed(model, texts))
        except Exception:  # noqa: BLE001 — векторы не должны ломать поиск
            log.warning("embed не ответил — поиск без векторов", exc_info=True)
            return None

    def _vector_search(self, q: str, limit: int) -> list[dict]:
        if self._vec is None:
            return []
        embedding = self._embed([q])
        if not embedding:
            return []
        _, model = self._resolve_embed()
        with self._uow() as uow:
            self._vec.ensure(uow.session, len(embedding[0]), model or "?")
            rows = self._vec.knn(uow.session, embedding[0], limit)
        for row in rows:
            row["title"] = self._item_title(row["item_key"])
        return rows

    def _item_title(self, item_key: str) -> str:
        if item_key.startswith("blk_"):
            try:
                return self._kb.get_block(item_key).meta.title
            except Exception:  # noqa: BLE001
                return item_key
        src_uid, _, ch = item_key.rpartition(":")
        return f"{src_uid} · глава {ch}"

    # --- индексация векторов (инкрементально по хэшу текста) ---

    def index_block_embeddings(self, block_uid: str) -> dict:
        """Векторы блока (job search_embed). Текст не менялся — skip."""
        if self._vec is None:
            return {"skipped": True, "reason": "vec-индекс недоступен"}
        try:
            block = self._kb.get_block(block_uid)
        except Exception:  # noqa: BLE001 — блок удалён
            return {"skipped": True, "reason": "блок не найден"}
        text = "\n".join([block.meta.title, block.meta.summary or "", block.content])
        return self._index_text("blk_", block_uid, text)

    def index_chapter_embeddings(self, source_uid: str, chapter: int, text: str) -> dict:
        """Векторы главы по тексту (FTS-индексация уже читала его)."""
        return self._index_text("chapter", f"{source_uid}:{chapter}", text)

    def _index_text(self, _kind: str, item_key: str, text: str) -> dict:
        from .infra.vec import text_hash as th

        chunks = chunk_text(text)
        combined = th("".join(chunks))
        with self._uow() as uow:
            if self._vec.item_hash(uow.session, item_key) == combined:
                return {"skipped": True, "reason": "текст не менялся", "chunks": len(chunks)}
        embeddings = self._embed(chunks)
        if embeddings is None:
            return {"skipped": True, "reason": "роль embed не настроена"}
        _, model = self._resolve_embed()
        with self._uow() as uow:
            vec0 = self._vec.ensure(uow.session, len(embeddings[0]), model or "?")
            if not vec0:
                log.info("vec0 недоступен — чанки индексируются c Python-fallback KNN")
            self._vec.upsert_item(uow.session, item_key, list(zip(chunks, embeddings, strict=False)))
        return {"indexed": True, "chunks": len(chunks), "vec0": vec0}

    # --- FTS: как раньше (события) ---

    def search_chunks(self, q: str, limit: int = 10) -> list[dict]:
        """Алиас search(scope=chapters) для совместимости с v1."""
        with self._uow() as uow:
            return self._fts.search_chapters(uow.session, q, limit)

    def on_block_saved(self, block_uid: str) -> None:
        """Переиндексировать один блок (события BlockSaved/BlockUpdated)."""
        from ..knowledge.domain import plain_text

        try:
            block = self._kb.get_block(block_uid)
        except Exception:  # noqa: BLE001 — блок мог быть удалён
            return
        body = plain_text(block.content)
        with self._uow() as uow:
            self._fts.upsert_block(
                uow.session,
                block_uid,
                block.meta.title,
                block.meta.summary or "",
                body,
                # категория входит в индекс: поиск «kubernetes» находит блоки ветки (R-19)
                " ".join([*block.meta.tags, block.meta.category_path or ""]),
            )

    def on_block_deleted(self, block_uid: str) -> None:
        """Убрать блок из индексов (событие BlockDeleted): FTS + векторы."""
        with self._uow() as uow:
            self._fts.delete_block(uow.session, block_uid)
            if self._vec is not None:
                self._vec.delete_item(uow.session, block_uid)

    def reindex_chapters(self, source_uid: str | None = None) -> None:
        """Пересобрать индекс глав: один источник или все (вручную)."""
        with self._uow() as uow:
            self._fts.reindex_chapters(uow.session, source_uid)

    def drop_source_index(self, source_uid: str) -> None:
        """Убрать главы источника из индексов (SourceDeleted)."""
        with self._uow() as uow:
            self._fts.delete_source(uow.session, source_uid)
            if self._vec is not None:
                keys = (
                    uow.session.execute(
                        text("SELECT DISTINCT item_key FROM vec_chunks WHERE item_key LIKE :pat"),
                        {"pat": f"{source_uid}:%"},
                    )
                    .scalars()
                    .all()
                )
                for key in keys:
                    self._vec.delete_item(uow.session, key)

    def reindex_blocks(self) -> None:
        """Пересобрать индекс блоков из базы знаний."""
        for meta in self._kb.list_blocks(limit=1000):
            self.on_block_saved(meta.uid)

    # --- статус для health (B-008) ---

    def vector_status(self) -> dict:
        """Роль embed и объём векторного индекса — для /api/health."""
        provider, model = self._resolve_embed()
        if self._vec is None:
            return {"embed_configured": provider is not None, "embed_model": model, "indexed_items": 0}
        with self._uow() as uow:
            indexed = self._vec.count_items(uow.session)
            state = self._vec.state(uow.session)
        total = len(self._kb.list_blocks(limit=1000))
        return {
            "embed_configured": provider is not None,
            "embed_model": model,
            "indexed_items": indexed,
            "pending_blocks": max(0, total - indexed),
            "index_model": state.get("model"),
        }
