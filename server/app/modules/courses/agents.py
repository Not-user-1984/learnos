"""Агент course_planner: план курса из библиотеки + веб-кандидатов."""

from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"


class CoursePlanItem(BaseModel):
    """Элемент плана."""

    item_type: str  # source | chapter | block | web
    title: str = ""
    source_uid: str | None = None
    chapter: int | None = None
    block_uid: str | None = None
    url: str | None = None
    note: str = ""


class CoursePlan(BaseModel):
    """Выход course_planner."""

    title: str
    topic: str
    description: str = ""
    category: str | None = None
    items: list[CoursePlanItem] = Field(default_factory=list, max_length=20)


course_planner = AgentSpec(
    name="course_planner",
    description="Собирает план курса по теме: источники из библиотеки, главы, блоки + веб-кандидаты.",
    prompt_path=AGENTS_DIR / "course_planner" / "prompt.md",
    model_role="structured",
    output_model=CoursePlan,
)


def register_agents(c) -> None:
    """Зарегистрировать планировщика курсов."""
    registry: AgentRegistry = c.agent_registry
    registry.register(course_planner)
