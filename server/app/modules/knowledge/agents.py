"""Агенты модуля knowledge: block_writer (генерация блока) и categorizer (подбор категории)."""

from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"


class ConceptOut(BaseModel):
    """Понятие из block_writer."""

    term: str = Field(max_length=80)
    definition: str = Field(max_length=300)


class PracticeOut(BaseModel):
    """Шаг практики из block_writer."""

    machine: str
    command: str
    explanation: str
    result: str | None = None


class SourceOut(BaseModel):
    """Ссылка блока на источник."""

    source: str
    chapter: int | None = None
    title: str = ""


class BlockWriterDraft(BaseModel):
    """Структурированный выход block_writer — вход для save_block."""

    title: str = Field(max_length=100)
    summary: str = Field(default="", max_length=280)
    kind: str = "lesson"
    concepts: list[ConceptOut] = Field(default_factory=list, max_length=12)
    theses: list[str] = Field(min_length=1, max_length=7)
    my_examples: list[str] = Field(default_factory=list)
    mermaid: str | None = None
    practice: list[PracticeOut] = Field(default_factory=list)
    weak_spots: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=8)
    category_suggestion: str | None = None
    sources: list[SourceOut] = Field(default_factory=list)


class CategorizerOutput(BaseModel):
    """Выход categorizer: путь существующей категории или новый узел."""

    path: str
    new_category_title: str | None = None


block_writer = AgentSpec(
    name="block_writer",
    description=(
        "Собирает BlockDraft из транскрипта сессии или переписки: "
        "понятия, тезисы, «как я понял», практика, дозакрепить."
    ),
    prompt_path=AGENTS_DIR / "block_writer" / "prompt.md",
    model_role="structured",
    output_model=BlockWriterDraft,
)

runbook_writer = AgentSpec(
    name="runbook_writer",
    description="Собирает runbook (kind: runbook) из practice_log сессии: команды, проверки, откат, грабли.",
    prompt_path=AGENTS_DIR / "runbook_writer" / "prompt.md",
    model_role="structured",
    output_model=BlockWriterDraft,
)

categorizer = AgentSpec(
    name="categorizer",
    description="Подбирает категорию блока из дерева kb/categories.yaml или предлагает новый узел.",
    prompt_path=AGENTS_DIR / "categorizer" / "prompt.md",
    model_role="fast",
    output_model=CategorizerOutput,
)


def register_agents(c) -> None:
    """Зарегистрировать агентов модуля в реестре."""
    registry: AgentRegistry = c.agent_registry
    registry.register(block_writer)
    registry.register(categorizer)
    registry.register(runbook_writer)
