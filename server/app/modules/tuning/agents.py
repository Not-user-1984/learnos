"""Агенты tuning: prompt_tuner (правка промптов) и agent_designer (конструктор новых агентов)."""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"

prompt_tuner = AgentSpec(
    name="prompt_tuner",
    description=(
        "Настраивает поведение агентов: пожелания пользователя → правки промптов (с подтверждением)."
    ),
    prompt_path=AGENTS_DIR / "prompt_tuner" / "prompt.md",
    model_role="chat",
    tools=frozenset(
        {
            "list_agent_prompts",
            "read_agent_prompt",
            "propose_prompt_change",
            "propose_change",
            "discard_prompt_change",
            "send_telegram_text",
        }
    ),
    max_steps=16,
)


class DesignerOut(BaseModel):
    """Выход конструктора агентов: драфт нового агента."""

    name: str = Field(max_length=40)
    description: str = Field(max_length=200)
    prompt: str = Field(min_length=40)
    tools: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(default="", max_length=300)


agent_designer = AgentSpec(
    name="agent_designer",
    description="Конструктор новых агентов: пожелание пользователя → драфт агента (промпт + инструменты).",
    prompt_path=AGENTS_DIR / "agent_designer" / "prompt.md",
    model_role="chat",
    tools=frozenset(),
    output_model=DesignerOut,
)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def valid_agent_name(name: str) -> bool:
    """Имя кастомного агента: латиница/цифры/подчёркивание, без конфликтов с режимами чата."""
    return bool(NAME_RE.match(name)) and ":" not in name


def register_agents(c) -> None:
    """Зарегистрировать настройщика и конструктора."""
    registry: AgentRegistry = c.agent_registry
    registry.register(prompt_tuner)
    registry.register(agent_designer)
