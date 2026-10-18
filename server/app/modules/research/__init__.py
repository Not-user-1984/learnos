"""Модуль «research»: веб-поиск и чтение страниц — инструменты ресёрча для всех агентов."""

from ...kernel.module import Module


class ResearchModule(Module):
    """Поиск (цепочка провайдеров, кэш + single-flight), извлечение статей, настройки связи."""

    name = "research"

    def wire(self, c) -> None:
        from .service import ResearchService

        c.research = ResearchService(c.settings, c.uow)
        try:
            c.research.refresh_connectivity()  # настройки из БД (поиск/прокси из UI)
        except Exception as e:  # noqa: BLE001 — БД может быть ещё не мигрирована
            from .connectivity import log

            log.info("настройки связи не загружены: %s", e)

    def routers(self, c):
        from .api import make_router

        return [make_router(c)]

    def tools(self, c):
        from .tools import research_tools

        return research_tools(c)
