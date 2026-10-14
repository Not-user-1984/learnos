"""Модуль «Обучение»: активности (прохождение источника), сессии (стейт-машина), практика."""

from ...kernel.module import Module


class LearningModule(Module):
    """Сессия честная: finish только из debrief; фейнман-этап обязателен."""

    name = "learning"

    def wire(self, c) -> None:
        from .infra.sql_repo import ActivityRepository, SessionRepository
        from .service import LearningService

        c.learning = LearningService(
            uow=c.uow,
            sessions=SessionRepository(),
            activities=ActivityRepository(),
            ids=c.ids,
            clock=c.clock,
            knowledge=c.knowledge,
            profile=c.profile,
        )

    def routers(self, c):
        from .api import make_router

        return [make_router(c.learning)]

    def tools(self, c):
        from .tools import learning_tools

        return learning_tools(c)
