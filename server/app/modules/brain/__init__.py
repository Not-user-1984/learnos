"""Модуль «Второй мозг» (B-007): capture/context для внешних нейронок через MCP."""

from ...kernel.module import Module


class BrainModule(Module):
    """Компактный фасад над knowledge/library/search; REST не нужен — только MCP-тулы."""

    name = "brain"

    def wire(self, c) -> None:
        from .service import BrainService

        c.brain = BrainService(knowledge=c.knowledge, library=c.library, search=c.search)

    def tools(self, c):
        from .tools import brain_tools

        return brain_tools(c)
