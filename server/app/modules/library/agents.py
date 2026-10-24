"""Агенты библиотеки: chapter_summarizer, source_overviewer, structure_curator."""

from pathlib import Path
from typing import Literal

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


class _CuratedEntry(BaseModel):
    """Классификация одной записи TOC куратором структуры."""

    idx: int = Field(ge=1)
    cls: Literal["chapter", "front_matter", "appendix"]
    number: int | None = Field(default=None, ge=1)


class _CuratorOut(BaseModel):
    """Выход structure_curator: по записи на каждую top-запись закладок."""

    entries: list[_CuratedEntry] = Field(min_length=1)


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


structure_curator = AgentSpec(
    name="structure_curator",
    description=(
        "Классифицирует записи закладок книги: chapter (с номером) / front_matter (мусор) / appendix. "
        "Один вызов на книгу, границы страниц не определяет."
    ),
    prompt_path=AGENTS_DIR / "structure_curator" / "prompt.md",
    model_role="fast",
    output_model=_CuratorOut,
)


def register_agents(c) -> None:
    """Зарегистрировать агентов библиотеки."""
    registry: AgentRegistry = c.agent_registry
    registry.register(chapter_summarizer)
    registry.register(source_overviewer)
    registry.register(structure_curator)
