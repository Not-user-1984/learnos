"""Модуль «База знаний»: блоки (MD-файлы + индекс), категории, версии."""

from ...kernel.module import Module


class KnowledgeModule(Module):
    """Блок создаётся только через сервис (сессия/разговор); файл — источник истины."""

    name = "knowledge"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .infra.md_store import MdBlockStore
        from .infra.sql_repo import BlockRepository, CategoryRepository
        from .service import KnowledgeService

        c.knowledge = KnowledgeService(
            uow=c.uow,
            files=MdBlockStore(c.settings.kb_dir),
            blocks=BlockRepository(),
            categories=CategoryRepository(),
            ids=c.ids,
            clock=c.clock,
            runtime=c.agent_runtime,
            profile=c.profile,
        )
        register_agents(c)

    def routers(self, c):
        from .api import make_alias_router, make_router

        return [make_router(c.knowledge), make_alias_router(c.knowledge)]

    def tools(self, c):
        from .tools import knowledge_tools

        return knowledge_tools(c)

    def subscribe(self, bus, c) -> None:
        pass  # knowledge — источник событий, не потребитель
