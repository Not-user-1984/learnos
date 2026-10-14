"""Модуль «Скиллы»: загрузка server/skills/* в реестр инструментов."""

from ...kernel.module import Module


class SkillsModule(Module):
    """Drop-in скиллы: SKILL.md + run.py, видны из MCP и от агентов."""

    name = "skills"

    def wire(self, c) -> None:
        from .loader import SkillLoader

        c.skills = SkillLoader(c.settings)

    def tools(self, c):
        return c.skills.tool_specs()
