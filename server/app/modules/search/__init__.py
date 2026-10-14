"""Модуль «Поиск»: FTS5 по блокам и главам, обновление по событиям."""

from ...kernel.module import Module


class SearchModule(Module):
    """FTS5-индексы blocks_fts и chapters_fts; создаются миграцией, обновляются событиями."""

    name = "search"

    def wire(self, c) -> None:
        from .infra.fts import FtsRepo
        from .service import SearchService

        c.search = SearchService(c.uow, FtsRepo(), c.knowledge)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.search)]

    def tools(self, c):
        from .tools import search_tools

        return search_tools(c)

    def subscribe(self, bus, c) -> None:
        from ..knowledge.events import BlockSaved, BlockUpdated
        from ..library.events import SourceProcessed

        bus.subscribe(BlockSaved.name(), lambda e: c.search.on_block_saved(e.block_uid))
        bus.subscribe(BlockUpdated.name(), lambda e: c.search.on_block_saved(e.block_uid))
        bus.subscribe(SourceProcessed.name(), lambda e: c.search.reindex_chapters())
