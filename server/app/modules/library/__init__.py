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
            research=c.research,
        )
        c.job_worker = JobWorker(c.library, c.agent_runtime)
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        # chat — get-or-create разговора главы для split-view (B-006)
        return [make_router(c.library, chat=c.chat)]

    def tools(self, c):
        from .tools import library_tools

        return library_tools(c)

    # подписка на SourceProcessed → reindex_chapters живёт в search-модуле
    # (одна подписка: раньше дублировалась здесь и там — переиндексация шла дважды)
