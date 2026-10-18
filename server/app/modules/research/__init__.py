"""Модуль «research»: веб-поиск и чтение страниц — инструменты ресёрча для всех агентов."""

from ...kernel.module import Module


class ResearchModule(Module):
    """Поиск (провайдер ddg, кэш + single-flight) и извлечение статей в текст/главы."""

    name = "research"

    def wire(self, c) -> None:
        from .service import ResearchService

        c.research = ResearchService(c.settings)

    def routers(self, c):
        return []

    def tools(self, c):
        from .tools import research_tools

        return research_tools(c)
