"""Инструменты модуля skills: save_skill — агентские скрипты под задачу (T-037)."""

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class SaveSkillArgs(BaseModel):
    """Аргументы сохранения своего скилла."""

    skill_name: str = Field(description="Имя скилла (латиница/цифры/_) — станет именем инструмента")
    skill_md: str = Field(
        description="Полный SKILL.md: frontmatter (name == skill_name, description, params) + описание"
    )
    run_py: str = Field(description="Код run.py с функцией main(**kwargs) → dict")


def skills_tools(c) -> list[ToolSpec]:
    """save_skill: создать/обновить СВОЙ скилл; скилл сразу доступен как инструмент."""
    svc = c.skills_service

    def save_skill(args: SaveSkillArgs, ctx: ToolContext) -> dict:
        return svc.save_skill(ctx.agent_name or "", args.skill_name, args.skill_md, args.run_py)

    return [
        ToolSpec(
            name="save_skill",
            module="skills",
            description=(
                "Создать/обновить СВОЙ скилл под задачу (парсер, обработчик) и сразу получить "
                "его как инструмент с именем skill_name. run.py — функция main(**kwargs), "
                "исполняется отдельным процессом с таймаутом; писать только в "
                "os.environ['LEARNOS_WRITE_DIR'], результат — return dict (print идёт в stdout). "
                "SKILL.md frontmatter: name (== skill_name), description, params "
                "(имя: {type, optional, default}). Править свой скилл можно повторными вызовами; "
                "builtin-скиллы и чужие — только через propose_change(kind='skill')."
            ),
            args_model=SaveSkillArgs,
            handler=save_skill,
            label="Сохраняю скилл",
            channels=frozenset({"agent"}),  # владелец = вызывающий агент, из MCP бессмысленно
        ),
    ]
