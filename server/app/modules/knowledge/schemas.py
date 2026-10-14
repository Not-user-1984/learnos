"""DTO базы знаний для REST и MCP."""

from pydantic import BaseModel, Field

from .domain import BlockSource


class ConceptIn(BaseModel):
    """Понятие на входе."""

    term: str = Field(max_length=80)
    definition: str = Field(max_length=300)


class PracticeStepIn(BaseModel):
    """Шаг практики на входе."""

    machine: str
    command: str
    explanation: str
    result: str | None = None
    verify: str | None = None
    cleanup: str | None = None


class SourceIn(BaseModel):
    """Ссылка на источник в драфте."""

    source: str
    chapter: int | None = None
    title: str = ""


class BlockDraftIn(BaseModel):
    """Драфт блока (вход для finish_session / save_note / update_block)."""

    title: str = Field(max_length=100)
    summary: str = Field(default="", max_length=280)
    kind: str = "lesson"
    concepts: list[ConceptIn] = Field(default_factory=list, max_length=12)
    theses: list[str] = Field(default_factory=list, max_length=7)
    my_examples: list[str] = Field(default_factory=list)
    mermaid: str | None = None
    practice: list[PracticeStepIn] = Field(default_factory=list)
    weak_spots: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=8)
    category_suggestion: str | None = None
    sources: list[SourceIn] = Field(default_factory=list)

    def to_domain(self):
        """Вход → доменный BlockDraft."""
        from .domain import BlockDraft as D
        from .domain import Concept, PracticeStep

        return D(
            title=self.title,
            summary=self.summary,
            kind=self.kind if self.kind in {"lesson", "note", "runbook"} else "lesson",
            concepts=tuple(Concept(c.term, c.definition) for c in self.concepts),
            theses=tuple(self.theses),
            my_examples=tuple(self.my_examples),
            mermaid=self.mermaid,
            practice=tuple(
                PracticeStep(p.machine, p.command, p.explanation, p.result) for p in self.practice
            ),
            weak_spots=tuple(self.weak_spots),
            open_questions=tuple(self.open_questions),
            links=tuple(self.links),
            tags=tuple(self.tags),
            category_suggestion=self.category_suggestion,
            sources=tuple(BlockSource(s.source, s.chapter, s.title) for s in self.sources),
        )


class BlockCard(BaseModel):
    """Карточка блока в списке."""

    block_uid: str
    title: str
    kind: str
    summary: str | None
    category_path: str | None
    category_status: str
    tags: list[str]
    sources: list[SourceIn]
    weak_spots_count: int
    version: int
    created_at: str
    updated_at: str


class BlockDetail(BlockCard):
    """Блок целиком с MD-телом."""

    content: str = ""
    session_uid: str | None = None
    conversation_uid: str | None = None
    activity_uid: str | None = None
    versions_count: int = 0
    links: list[str] = Field(default_factory=list)
    back_links: list[str] = Field(default_factory=list)


class VersionInfo(BaseModel):
    """Строка истории версий."""

    version: int
    reason: str | None
    conversation_uid: str | None
    created_at: str
    size: int


class CategoryNode(BaseModel):
    """Узел дерева категорий со счётчиком."""

    path: str
    title: str
    color: str | None = None
    icon: str | None = None
    count: int = 0
    children: list["CategoryNode"] = Field(default_factory=list)


class CategoryIn(BaseModel):
    """Создание/правка категории."""

    path: str
    title: str
    color: str | None = None
    icon: str | None = None
    sort: int = 0


class TagCount(BaseModel):
    """Тег с числом блоков."""

    tag: str
    count: int
