"""Модуль «Повторение»: SM-2 по блокам, вопрос дня в Telegram."""

from ...kernel.module import Module


class ReviewModule(Module):
    """Закрепление: блоки со «Дозакрепить» и созревшие по интервалу; оценка ответа агентом."""

    name = "review"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .infra.sql_repo import ReviewRepository
        from .service import ReviewService

        c.review = ReviewService(
            uow=c.uow,
            repo=ReviewRepository(),
            knowledge=c.knowledge,
            runtime=c.agent_runtime,
            profile=c.profile,
            clock=c.clock,
        )
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.review)]

    def tools(self, c):
        from .tools import review_tools

        return review_tools(c)
