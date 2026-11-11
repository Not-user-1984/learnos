"""Инструменты tuning для агента-настройщика промптов."""

from dataclasses import asdict as _asdict
from typing import Literal

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class NoArgs(BaseModel):
    """Без аргументов."""


class ReadPromptArgs(BaseModel):
    """Чтение промпта агента."""

    agent: str = Field(description="Имя агента")


class StageChangeArgs(BaseModel):
    """Черновик правки промпта (применяется только после подтверждения пользователем)."""

    agent: str = Field(description="Имя агента")
    new_content: str = Field(description="Новое содержимое промпта")
    summary: str = Field(description="Короткое описание правки")


class ProposeChangeArgs(BaseModel):
    """Черновик правки промпта или builtin-скилла (подтверждение — карточкой у человека)."""

    kind: Literal["prompt", "skill"] = Field(default="prompt", description="Правка промпта или скилла")
    target: str = Field(description="Агент (kind=prompt) или builtin-скилл (kind=skill)")
    new_content: str = Field(description="Новое содержимое")
    summary: str = Field(description="Короткое описание правки")
    file: str = Field(default="run.py", description="kind=skill: run.py | SKILL.md")


class ChangeIdArgs(BaseModel):
    """Ссылка на черновик правки."""

    change_id: int = Field(description="id черновика правки")


def tuning_tools(c) -> list[ToolSpec]:
    """Инструменты настройки агентов."""
    svc = c.tuning

    def list_agent_prompts(args: NoArgs, ctx: ToolContext) -> dict:
        del ctx
        return {"agents": [_asdict(p) for p in svc.list_prompts()]}

    def read_agent_prompt(args: ReadPromptArgs, ctx: ToolContext) -> dict:
        del ctx
        return svc.read_prompt(args.agent)

    def propose_prompt_change(args: StageChangeArgs, ctx: ToolContext) -> dict:
        return svc.stage_change(args.agent, args.new_content, args.summary, ctx.conversation_uid)

    def propose_change(args: ProposeChangeArgs, ctx: ToolContext) -> dict:
        if args.kind == "skill":
            return svc.stage_skill_change(
                args.target, args.file, args.new_content, args.summary, ctx.conversation_uid
            )
        return svc.stage_change(args.target, args.new_content, args.summary, ctx.conversation_uid)

    def discard_prompt_change(args: ChangeIdArgs, ctx: ToolContext) -> dict:
        del ctx
        return svc.reject_change(args.change_id)

    return [
        ToolSpec(
            name="list_agent_prompts",
            module="tuning",
            description="Промпты всех агентов LearnOS: имя, описание файла, есть ли переопределение.",
            args_model=NoArgs,
            handler=list_agent_prompts,
            label="Промпты агентов",
        ),
        ToolSpec(
            name="read_agent_prompt",
            module="tuning",
            description="Полный текущий промпт агента (system-инструкция).",
            args_model=ReadPromptArgs,
            handler=read_agent_prompt,
            label="Читаю промпт",
        ),
        ToolSpec(
            name="propose_prompt_change",
            module="tuning",
            description=(
                "Предложить правку промпта: полный новый текст + описание. "
                "Применяется только после «Применить» в карточке у пользователя. "
                "То же, что propose_change(kind='prompt')."
            ),
            args_model=StageChangeArgs,
            handler=propose_prompt_change,
            label="Готовлю правку промпта",
        ),
        ToolSpec(
            name="propose_change",
            module="tuning",
            description=(
                "Предложить правку карточкой с диффом: kind=prompt — промпт агента "
                "(target — имя агента, полный новый текст); kind=skill — builtin-скилл "
                "(target — имя скилла, file — run.py | SKILL.md). "
                "Применяется только после «Применить» у пользователя; свои агентские "
                "скиллы правятся свободно через save_skill."
            ),
            args_model=ProposeChangeArgs,
            handler=propose_change,
            label="Готовлю правку",
        ),
        ToolSpec(
            name="discard_prompt_change",
            module="tuning",
            description="Отозвать предложенную правку промпта.",
            args_model=ChangeIdArgs,
            handler=discard_prompt_change,
            label="Отзываю правку",
        ),
    ]
