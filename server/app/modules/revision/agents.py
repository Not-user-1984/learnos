"""Агент-аудитор ревизии кода (T-038): read-only доступ, задачи, ветки agent/*."""

from pathlib import Path

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"

auditor = AgentSpec(
    name="auditor",
    description=(
        "Аудитор кодовой базы: читает репозиторий LearnOS read-only, находит проблемы и "
        "улучшения, создаёт задачи; простые правки вне guard-листа готовит веткой agent/*."
    ),
    prompt_path=AGENTS_DIR / "auditor" / "prompt.md",
    tools=frozenset({"repo_list", "repo_read", "create_task_file", "git_prepare_change", "run_checks"}),
    max_steps=40,
)


def register_agents(c) -> None:
    """Зарегистрировать аудитора в реестре агентов."""
    registry: AgentRegistry = c.agent_registry
    registry.register(auditor)
