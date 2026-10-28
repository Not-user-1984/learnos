"""Модуль «Скиллы»: builtin из server/skills и агентские из data/agent-skills (T-037)."""

from ...kernel.module import Module


class SkillsModule(Module):
    """Drop-in скиллы: SKILL.md + run.py, видны из MCP и от агентов; агентские — песочница."""

    name = "skills"

    def wire(self, c) -> None:
        from .loader import SkillLoader
        from .service import SkillsService

        c.skills = SkillLoader(c.settings)
        c.skills_service = SkillsService(c.settings, c.skills, c.tools, c.agent_registry)

    def tools(self, c):
        from .tools import skills_tools

        return c.skills.tool_specs() + skills_tools(c)
