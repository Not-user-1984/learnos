"""Модуль «Поиск»: FTS5 + векторы (B-008) по блокам и главам, обновление по событиям."""

from ...kernel.module import Module


class SearchModule(Module):
    """FTS5-индексы blocks_fts/chapters_fts и векторный индекс vec_chunks; события."""

    name = "search"

    def wire(self, c) -> None:
        from .infra.fts import FtsRepo
        from .infra.vec import VecRepo
        from .service import SearchService

        c.search = SearchService(c.uow, FtsRepo(), c.knowledge, vec=VecRepo(), router=c.llm_router)

        # фоновая векторная индексация — job'ой в общем воркере (B-008)
        def _embed_job(job: dict) -> dict:
            kind, _, ref = (job.get("target") or "").partition(":")
            if kind == "block":
                return c.search.index_block_embeddings(ref)
            if kind == "source":
                total = 0
                for ch in c.library.list_chapters(ref):
                    part = c.library.read_chapter(ref, ch["idx"], 0, 50000)
                    out = c.search.index_chapter_embeddings(ref, ch["idx"], part["text"])
                    total += out.get("chunks", 0)
                return {"indexed": True, "chunks": total}
            return {"skipped": True, "reason": f"неизвестный target {job.get('target')}"}

        c.job_worker.register_handler("search_embed", _embed_job)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.search)]

    def tools(self, c):
        from .tools import search_tools

        return search_tools(c)

    def subscribe(self, bus, c) -> None:
        from ..knowledge.events import BlockDeleted, BlockSaved, BlockUpdated
        from ..library.events import SourceDeleted, SourceProcessed

        def _on_block_saved(block_uid: str) -> None:
            c.search.on_block_saved(block_uid)
            # векторы — фоном: не блокировать запрос пользователя (B-008)
            c.job_worker.enqueue("search_embed", f"block:{block_uid}")

        bus.subscribe(BlockSaved.name(), lambda e: _on_block_saved(e.block_uid))
        bus.subscribe(BlockUpdated.name(), lambda e: _on_block_saved(e.block_uid))
        bus.subscribe(BlockDeleted.name(), lambda e: c.search.on_block_deleted(e.block_uid))
        bus.subscribe(SourceProcessed.name(), lambda e: _on_source_processed(c, e.source_uid))
        bus.subscribe(SourceDeleted.name(), lambda e: c.search.drop_source_index(e.source_uid))


def _on_source_processed(c, source_uid: str) -> None:
    """Главы источника: FTS сразу, векторы — фоновой job'ой."""
    c.search.reindex_chapters(source_uid)
    c.job_worker.enqueue("search_embed", f"source:{source_uid}")
