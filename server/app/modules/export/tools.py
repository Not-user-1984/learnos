"""Инструмент экспорта (MCP + агенты)."""

from pydantic import BaseModel

from ...kernel.tools.spec import ToolContext, ToolSpec


class ExportArgs(BaseModel):
    """export_markdown: склеенный MD для передачи другой нейронке."""

    scope: str = "all"  # block | category | course | source | all
    id: str | None = None
    max_chars: int | None = None


def export_tools(c) -> list[ToolSpec]:
    """Инструмент экспорта."""
    svc = c.export

    def export_markdown(args: ExportArgs, ctx: ToolContext):
        del ctx
        result = svc.markdown(args.scope, args.id, args.max_chars)
        return {"content": result["content"], "blocks": result["blocks"], "truncated": result["truncated"]}

    return [
        ToolSpec(
            name="export_markdown",
            module="export",
            description=(
                "Склеенный Markdown выгрузки (block|category|course|source|all) — "
                "передать другой нейронке или в Obsidian."
            ),
            args_model=ExportArgs,
            handler=export_markdown,
            label="Экспорт",
        )
    ]
