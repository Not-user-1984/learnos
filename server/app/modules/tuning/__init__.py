"""Модуль «Tuning»: настройка поведения агентов правкой промптов через диалог."""

from ...kernel.module import Module


class TuningModule(Module):
    """Настройщик промптов: предлагает правки, человек подтверждает; override в data/prompts."""

    name = "tuning"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .service import TuningService

        c.tuning = TuningService(c.uow, c.settings, c.agent_registry)
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.tuning)]

    def tools(self, c):
        from .tools import tuning_tools

        return tuning_tools(c)
