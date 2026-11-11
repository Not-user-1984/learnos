"""Модуль «Чат»: разговоры, сообщения, SSE-стриминг, агенты-тьюторы."""

from ...kernel.module import Module


class ChatModule(Module):
    """Режимы free / quick / session / tuning / root (оркестратор) + agent:<имя>."""

    name = "chat"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .cards import CardState
        from .infra.sql_repo import ConversationRepository, MessageRepository
        from .service import ChatService

        conversations = ConversationRepository()
        messages = MessageRepository()
        c.chat = ChatService(
            uow=c.uow,
            conversations=conversations,
            messages=messages,
            runtime=c.agent_runtime,
            registry=c.agent_registry,
            tools=c.tools,
            router=c.llm_router,
            learning=c.learning,
            library=c.library,
            knowledge=c.knowledge,
            profile=c.profile,
            recorder=c.run_recorder,
            ids=c.ids,
            clock=c.clock,
            settings=c.settings,
        )
        # resolve карточек-решений: статус живёт в БД, не в useState веба (B-003)
        c.chat_cards = CardState(c.uow, conversations, messages)
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.chat, cards=c.chat_cards)]

    def tools(self, c):
        from .tools import chat_tools

        return chat_tools(c)
