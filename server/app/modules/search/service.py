"""Сервис поиска: FTS5 по блокам и главам."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...kernel.db import UnitOfWorkFactory

if TYPE_CHECKING:
    from .infra.fts import FtsRepo

log = logging.getLogger("learnos.search")


class SearchService:
    """Поиск с областью: blocks | chapters | all. Обновление индекса — по событиям."""

    def __init__(self, uow: UnitOfWorkFactory, fts: FtsRepo, knowledge) -> None:
        self._uow = uow
        self._fts = fts
        self._knowledge = knowledge

    def search(self, q: str, scope: str = "all", limit: int = 10) -> dict:
        """Поиск по FTS5; блоки и главы отдельными списками."""
        if scope not in {"blocks", "chapters", "all"}:
            scope = "all"
        out: dict = {"query": q, "scope": scope}
        with self._uow() as uow:
            if scope in {"blocks", "all"}:
                out["blocks"] = self._fts.search_blocks(uow.session, q, limit)
            if scope in {"chapters", "all"}:
                out["chunks"] = self._fts.search_chapters(uow.session, q, limit)
        return out

    def search_chunks(self, q: str, limit: int = 10) -> list[dict]:
        """Алиас search(scope=chapters) для совместимости с v1."""
        with self._uow() as uow:
            return self._fts.search_chapters(uow.session, q, limit)

    def on_block_saved(self, block_uid: str) -> None:
        """Переиндексировать один блок (события BlockSaved/BlockUpdated)."""
        from ..knowledge.domain import plain_text

        try:
            block = self._knowledge.get_block(block_uid)
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
        """Убрать блок из поискового индекса (событие BlockDeleted)."""
        with self._uow() as uow:
            self._fts.delete_block(uow.session, block_uid)

    def reindex_chapters(self, source_uid: str | None = None) -> None:
        """Пересобрать индекс глав: один источник или все (вручную)."""
        with self._uow() as uow:
            self._fts.reindex_chapters(uow.session, source_uid)

    def drop_source_index(self, source_uid: str) -> None:
        """Убрать главы источника из индекса (SourceDeleted — без полной пересборки)."""
        with self._uow() as uow:
            self._fts.delete_source(uow.session, source_uid)

    def reindex_blocks(self) -> None:
        """Пересобрать индекс блоков из базы знаний."""
        for meta in self._knowledge.list_blocks(limit=1000):
            self.on_block_saved(meta.uid)
