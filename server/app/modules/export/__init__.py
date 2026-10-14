"""Модуль «Экспорт»: MD и ZIP выгрузки базы знаний, источников, курсов."""

from ...kernel.module import Module


class ExportModule(Module):
    """Экспорт без своей БД: читает публичные сервисы knowledge/library/courses."""

    name = "export"

    def wire(self, c) -> None:
        from .service import ExportService

        c.export = ExportService(c.knowledge, c.library, c.courses)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.export)]

    def tools(self, c):
        from .tools import export_tools

        return export_tools(c)
