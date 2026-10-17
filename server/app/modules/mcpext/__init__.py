"""Модуль «mcpext»: сторонние MCP-серверы — подключение из UI, инструменты агентам."""

from pydantic import BaseModel

from ...kernel.module import Module
from ...kernel.tools.spec import ToolContext, ToolSpec


class NoArgs(BaseModel):
    """Без аргументов."""


def _mcpext_tools(c) -> list[ToolSpec]:
    svc = c.mcpext

    def list_external_mcps(args: NoArgs, ctx: ToolContext):
        del args, ctx
        return svc.list_mcps()

    return [
        ToolSpec(
            name="list_external_mcps",
            module="mcpext",
            description=(
                "Сторонние MCP-подключения: имя, url, статус, инструменты "
                "(обёртки mcp_<сервер>_<инструмент>)."
            ),
            args_model=NoArgs,
            handler=list_external_mcps,
            label="Внешние MCP",
        )
    ]


class McpExtModule(Module):
    """Внешние MCP: ссылки/конфиги из настроек; инструменты появляются у агентов без рестарта."""

    name = "mcpext"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .service import McpExtService

        c.mcpext = McpExtService(c.uow, c.tools, c.agent_runtime)
        register_agents(c)
        # обёртки из БД регистрируются в lifespan, после миграций (нерабочие серверы не мешают старту)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.mcpext)]

    def tools(self, c):
        # статический инструмент-каталог; обёртки серверов регистрируются динамически сервисом
        return _mcpext_tools(c)
