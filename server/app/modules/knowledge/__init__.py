"""Модуль «База знаний»: блоки (MD-файлы + индекс), категории, версии."""

from ...kernel.module import Module


class KnowledgeModule(Module):
    """Блок создаётся только через сервис (сессия/разговор); файл — источник истины."""

    name = "knowledge"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .infra.md_store import MdBlockStore
        from .infra.sql_repo import BlockRepository, CategoryRepository
        from .infra.versions_repo import BlockVersionsRepository
        from .service import KnowledgeService
        from .usecases.blocks_ops import BlocksOpsUseCases
        from .usecases.categories import CategoryUseCases
        from .usecases.generation import GenerationUseCases

        c.knowledge = KnowledgeService(
            uow=c.uow,
            files=MdBlockStore(c.settings.kb_dir),
            blocks=BlockRepository(),
            versions=BlockVersionsRepository(),
            categories=CategoryRepository(),
            ids=c.ids,
            clock=c.clock,
            runtime=c.agent_runtime,
            profile=c.profile,
        )
        c.knowledge.bind_generation(GenerationUseCases(c.knowledge))
        c.knowledge.bind_categories(CategoryUseCases(c.knowledge))
        c.knowledge.bind_blocks_ops(BlocksOpsUseCases(c.knowledge))
        register_agents(c)

    def routers(self, c):
        from .api import make_alias_router, make_router

        return [make_router(c.knowledge), make_alias_router(c.knowledge)]

    def tools(self, c):
        from .tools import knowledge_tools

        return knowledge_tools(c)

    def subscribe(self, bus, c) -> None:
        pass  # knowledge — источник событий, не потребитель
