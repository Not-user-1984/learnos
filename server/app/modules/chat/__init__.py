"""Модуль «Чат»: разговоры, сообщения, SSE-стриминг, агенты-тьюторы."""

from ...kernel.module import Module


class ChatModule(Module):
    """Три режима: free / quick / session. Агент выбирается по mode разговора."""

    name = "chat"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .infra.sql_repo import ConversationRepository, MessageRepository
        from .service import ChatService

        c.chat = ChatService(
            uow=c.uow,
            conversations=ConversationRepository(),
            messages=MessageRepository(),
            runtime=c.agent_runtime,
            registry=c.agent_registry,
            tools=c.tools,
            router=c.llm_router,
            learning=c.learning,
            library=c.library,
            knowledge=c.knowledge,
            profile=c.profile,
            ids=c.ids,
            clock=c.clock,
            settings=c.settings,
        )
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.chat)]
