"""Инструмент экспорта (MCP + агенты)."""

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class ExportArgs(BaseModel):
    """export_markdown: склеенный MD для передачи другой нейронке."""

    scope: str = Field(default="all", description="block | category | course | source | all")
    id: str | None = Field(default=None, description="uid выбранного объекта (для block/category/…)")
    max_chars: int | None = Field(default=None, description="Лимит символов (обрезка — truncated=true)")


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
