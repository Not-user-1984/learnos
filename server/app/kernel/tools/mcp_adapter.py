"""Адаптер реестра инструментов в MCP-серверы (общий /mcp и узкие /mcp/<module>)."""

from mcp.server.mcpserver import MCPServer

from .registry import ToolRegistry
from .spec import ToolContext, ToolSpec


def _build_fn(spec: ToolSpec, registry: ToolRegistry):
    """Обёртка с явной сигнатурой из pydantic-полей (exec-кодогенерация, как в скиллах v1).

    Аннотации — Annotated[тип, FieldInfo из ToolSpec]: MCP SDK строит inputSchema
    по сигнатуре, и так description/constraints/default полей доходят до клиента (B-007).
    Сложные типы передаются алиасами в globals функции — pydantic SDK резолвит
    аннотации по globals, поэтому все классы кладём в namespace явно.
    """
    from typing import Annotated

    from pydantic import Field as PydField

    fields = list(spec.args_model.model_fields.items())
    required = [(n, f) for n, f in fields if f.is_required()]
    optional = [(n, f) for n, f in fields if not f.is_required()]
    ordered = required + optional
    namespace: dict = {"_registry": registry, "_ctx": lambda: ToolContext(channel="mcp")}
    params = []
    for n, f in required:
        alias = f"_A{len(namespace)}"
        namespace[alias] = Annotated[(f.annotation, f)]
        params.append(f"{n}: {alias}")
    for n, f in optional:
        alias = f"_A{len(namespace)}"
        if f.default_factory is not None:
            # default_factory в сигнатуре невозможна после дефолтов, а pydantic не
            # берёт default+default_factory одновременно: материализуем дефолт фабрикой
            namespace[alias] = Annotated[
                (
                    f.annotation,
                    PydField(default=f.default_factory(), description=f.description),
                )
            ]
            params.append(f"{n}: {alias} = {f.default_factory()!r}")
        else:
            namespace[alias] = Annotated[(f.annotation, f)]
            params.append(f"{n}: {alias} = {f.default!r}")
    call_args = ", ".join(f"{n}={n}" for n, _ in ordered)
    body = f"    return _registry.call({spec.name!r}, dict({call_args}), _ctx())\n"
    src = f"def _tool({', '.join(params)}):\n{body}"
    exec(src, namespace)  # noqa: S102 — контролируемая кодогенерация своей схемы
    fn = namespace["_tool"]
    fn.__name__ = spec.name
    fn.__doc__ = spec.description
    return fn


def _description(spec: ToolSpec) -> str:
    """Описание тула с пометкой deprecated (дубли B-007 не удаляем, а помечаем)."""
    if spec.deprecated:
        return f"[УСТАРЕЛО: {spec.deprecated}] {spec.description}"
    return spec.description


def build_mcp_server(
    name: str,
    registry: ToolRegistry,
    tools: list[ToolSpec],
    instructions: str | None = None,
    resources: list | None = None,
) -> MCPServer:
    """MCPServer с переданным набором инструментов (и опционально ресурсами)."""
    server = MCPServer(name=name, instructions=instructions or f"Инструменты LearnOS: {name}")
    for spec in tools:
        server.add_tool(_build_fn(spec, registry), name=spec.name, description=_description(spec))
    for resource in resources or []:
        server.add_resource(resource)
    return server
