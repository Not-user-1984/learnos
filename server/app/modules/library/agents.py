"""Агент chapter_summarizer: summary и key points по одной главе."""

from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"


class _ChapterOut(BaseModel):
    """Выход chapter_summarizer."""

    summary: str = Field(max_length=600)
    key_points: list[str] = Field(default_factory=list, max_length=7)
    has_exercises: bool = False


class _OverviewOut(BaseModel):
    """Выход source_overviewer: цельный обзор книги."""

    summary: str = Field(max_length=1600)


source_overviewer = AgentSpec(
    name="source_overviewer",
    description="Пишет обзор источника (5–8 предложений) из конспектов глав.",
    prompt_path=AGENTS_DIR / "source_overviewer" / "prompt.md",
    model_role="fast",
    output_model=_OverviewOut,
)


chapter_summarizer = AgentSpec(
    name="chapter_summarizer",
    description="Сжимает главу источника: 3–5 предложений summary, 3–7 ключевых пунктов, флаг упражнений.",
    prompt_path=AGENTS_DIR / "chapter_summarizer" / "prompt.md",
    model_role="fast",
    output_model=_ChapterOut,
)


def register_agents(c) -> None:
    """Зарегистрировать агента библиотеки."""
    registry: AgentRegistry = c.agent_registry
    registry.register(chapter_summarizer)
    registry.register(source_overviewer)
