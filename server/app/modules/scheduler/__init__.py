"""Модуль «Планировщик» (B-010): встроенный cron — агенты и джобы по расписанию."""

from ...kernel.module import Module


class SchedulerModule(Module):
    """Тик раз в минуту в lifespan; лок на запуск; дефолты выключены (квота GLM)."""

    name = "scheduler"

    def wire(self, c) -> None:
        from .infra.sql_repo import ScheduleRepository
        from .service import SchedulerService

        c.scheduler = SchedulerService(
            uow=c.uow,
            repo=ScheduleRepository(),
            runtime=c.agent_runtime,
            registry=c.agent_registry,
            review=c.review,
            messenger=c.messenger,
            settings=c.settings,
        )

    def routers(self, c):
        from .api import make_router

        return [make_router(c.scheduler)]
