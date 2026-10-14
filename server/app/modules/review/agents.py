"""Агент review_examiner: вопрос по блоку и оценка ответа."""

from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"


class ExaminerOut(BaseModel):
    """Выход review_examiner: качество 0–5 и обратная связь (или вопрос, если вход — «сформулируй»)."""

    quality: int = Field(ge=0, le=5, default=3)
    feedback: str


review_examiner = AgentSpec(
    name="review_examiner",
    description="Повторения: вопрос «объясни своими словами» и оценка ответа 0–5 с обратной связью.",
    prompt_path=AGENTS_DIR / "review_examiner" / "prompt.md",
    model_role="fast",
    output_model=ExaminerOut,
)


def register_agents(c) -> None:
    """Зарегистрировать экзаменатора повторений."""
    registry: AgentRegistry = c.agent_registry
    registry.register(review_examiner)
