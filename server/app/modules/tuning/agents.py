"""Агент prompt_tuner: настройка поведения агентов правкой промптов."""

from pathlib import Path

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
            "discard_prompt_change",
            "send_telegram_text",
        }
    ),
    max_steps=16,
)


def register_agents(c) -> None:
    """Зарегистрировать настройщика."""
    registry: AgentRegistry = c.agent_registry
    registry.register(prompt_tuner)
