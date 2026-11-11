"""Модуль «Сегодня»: дашборд «что делать дальше» из сервисов других модулей (B-005)."""

from ...kernel.module import Module


class TodayModule(Module):
    """Один снимок состояния системы: сессия, курсы, чтение, повторения, входящие."""

    name = "today"

    def wire(self, c) -> None:
        from .service import TodayService

        c.today = TodayService(
            learning=c.learning,
            courses=c.courses,
            library=c.library,
            knowledge=c.knowledge,
            review=c.review,
            chat=c.chat,
        )

    def routers(self, c):
        from .api import make_router

        return [make_router(c.today)]
