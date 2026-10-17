"""Инструменты tuning для агента-настройщика промптов."""

from dataclasses import asdict as _asdict

from pydantic import BaseModel

from ...kernel.tools.spec import ToolContext, ToolSpec


class NoArgs(BaseModel):
    """Без аргументов."""


class ReadPromptArgs(BaseModel):
    """Чтение промпта агента."""

    agent: str


class StageChangeArgs(BaseModel):
    """Черновик правки промпта (применяется только после подтверждения пользователем)."""

    agent: str
    new_content: str
    summary: str


class ChangeIdArgs(BaseModel):
    """Ссылка на черновик правки."""

    change_id: int


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
                "Применяется только после «Применить» в карточке у пользователя."
            ),
            args_model=StageChangeArgs,
            handler=propose_prompt_change,
            label="Готовлю правку промпта",
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
