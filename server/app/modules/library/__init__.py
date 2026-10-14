"""Модуль «Библиотека»: источники (PDF/YouTube/web), главы, обработка (jobs)."""

from ...kernel.module import Module


class LibraryModule(Module):
    """Источники живут независимо от курсов; обработка — фоновые jobs."""

    name = "library"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .infra.sql_repo import ChapterRepository, JobRepository, SourceRepository
        from .service import LibraryService
        from .worker import JobWorker

        c.library = LibraryService(
            uow=c.uow,
            sources=SourceRepository(),
            chapters=ChapterRepository(),
            jobs=JobRepository(),
            skills=c.skills,
            ids=c.ids,
            clock=c.clock,
            settings=c.settings,
            runtime=c.agent_runtime,
        )
        c.job_worker = JobWorker(c.library, c.agent_runtime)
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.library)]

    def tools(self, c):
        from .tools import library_tools

        return library_tools(c)

    def subscribe(self, bus, c) -> None:
        from .events import SourceProcessed

        bus.subscribe(SourceProcessed.name(), lambda _event: c.search.reindex_chapters())
