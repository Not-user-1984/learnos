"""Модуль «Tuning»: настройка поведения агентов правкой промптов через диалог."""

from ...kernel.module import Module


class TuningModule(Module):
    """Настройщик промптов: предлагает правки, человек подтверждает; override в data/prompts."""

    name = "tuning"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .service import TuningService

        c.tuning = TuningService(
            c.uow, c.settings, c.agent_registry, c.agent_runtime, c.tools, skills=c.skills_service
        )
        register_agents(c)
        # кастомные агенты из БД — в реестр сразу (созданные через конструктор в UI)
        c.tuning.load_custom_agents()

    def routers(self, c):
        from .api import make_router

        return [make_router(c.tuning)]

    def tools(self, c):
        from .tools import tuning_tools

        return tuning_tools(c)
