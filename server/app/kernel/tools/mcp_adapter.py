"""Адаптер реестра инструментов в MCP-серверы (общий /mcp и узкие /mcp/<module>)."""

from mcp.server.mcpserver import MCPServer

from .registry import ToolRegistry
from .spec import ToolContext, ToolSpec


def _build_fn(spec: ToolSpec, registry: ToolRegistry):
    """Обёртка с явной сигнатурой из pydantic-полей (exec-кодогенерация, как в скиллах v1).

    Сложные типы передаются алиасами _T<i> в globals функции — pydantic SDK резолвит
    аннотации по globals, поэтому все классы кладём в namespace явно.
    """
    fields = list(spec.args_model.model_fields.items())
    required = [(n, f) for n, f in fields if f.is_required()]
    optional = [(n, f) for n, f in fields if not f.is_required()]
    ordered = required + optional

    namespace: dict = {"_registry": registry, "_ctx": lambda: ToolContext(channel="mcp")}
    params = []
    for n, f in required:
        alias = f"_T{len(namespace)}"
        namespace[alias] = f.annotation
        params.append(f"{n}: {alias}")
    for n, f in optional:
        alias = f"_T{len(namespace)}"
        namespace[alias] = f.annotation
        default = repr(f.default)
        params.append(f"{n}: {alias} = {default}")
    call_args = ", ".join(f"{n}={n}" for n, _ in ordered)
    body = f"    return _registry.call({spec.name!r}, dict({call_args}), _ctx())\n"
    src = f"def _tool({', '.join(params)}):\n{body}"
    exec(src, namespace)  # noqa: S102 — контролируемая кодогенерация своей схемы
    fn = namespace["_tool"]
    fn.__name__ = spec.name
    fn.__doc__ = spec.description
    return fn


def build_mcp_server(name: str, registry: ToolRegistry, tools: list[ToolSpec]) -> MCPServer:
    """MCPServer с переданным набором инструментов реестра."""
    server = MCPServer(name=name, instructions=f"Инструменты LearnOS: {name}")
    for spec in tools:
        server.add_tool(_build_fn(spec, registry), name=spec.name, description=spec.description)
    return server
