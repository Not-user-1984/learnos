"""Инструменты модуля search (MCP + агенты)."""

from pydantic import BaseModel

from ...kernel.tools.spec import ToolContext, ToolSpec


class SearchArgs(BaseModel):
    """search по блокам и/или главам."""

    q: str
    scope: str = "all"  # blocks | chapters | all
    limit: int = 10


class ChunksArgs(BaseModel):
    """search_chunks — алиас v1."""

    query: str
    limit: int = 10


def search_tools(c) -> list[ToolSpec]:
    """Инструменты поиска."""
    svc = c.search

    def search(args: SearchArgs, ctx: ToolContext):
        del ctx
        return svc.search(args.q, args.scope, args.limit)

    def search_chunks(args: ChunksArgs, ctx: ToolContext):
        del ctx
        return svc.search_chunks(args.query, args.limit)

    return [
        ToolSpec(
            name="search",
            module="search",
            description="FTS5-поиск: q, scope: blocks|chapters|all.",
            args_model=SearchArgs,
            handler=search,
            label="Ищу",
        ),
        ToolSpec(
            name="search_chunks",
            module="search",
            description="Поиск по главам источников (совместимость).",
            args_model=ChunksArgs,
            handler=search_chunks,
            label="Ищу по главам",
        ),
    ]
