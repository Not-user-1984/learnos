"""Инструменты модуля library (MCP + агенты)."""

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec
from .schemas import SourceCreate


class ProcessArgs(BaseModel):
    """process_source: запускает job обработки."""

    source_id: str | int
    force: bool = False


class RefArgs(BaseModel):
    """Ссылка на источник (uid или id)."""

    source: str | int


class ListSourcesArgs(BaseModel):
    """list_sources с фильтром."""

    kind: str | None = None


class ReadChapterArgs(BaseModel):
    """read_chapter: порция текста главы."""

    source_id: str | int
    chapter: int
    offset: int = 0
    limit: int = Field(default=6000, ge=500, le=24000)


class ResearchArgs(BaseModel):
    """research_sources: веб-поиск кандидатов."""

    topic: str
    limit: int = 8


class GetJobArgs(BaseModel):
    """Статус job."""

    job_id: int


def library_tools(c) -> list[ToolSpec]:
    """Инструменты библиотеки."""
    svc = c.library

    def add_source(args: SourceCreate, ctx: ToolContext):
        del ctx
        result = svc.add_source(args.kind, args.title, args.url, args.local_path, course_id=args.course_id)
        if args.course_id and hasattr(c, "courses"):
            c.courses.add_item(args.course_id, item_type="source", source_id=result["id"])
        return result

    def list_sources(args: ListSourcesArgs, ctx: ToolContext):
        del ctx
        return svc.list_sources(kind=args.kind)

    def get_source(args: RefArgs, ctx: ToolContext):
        del ctx
        return svc.get_source(args.source)

    def process_source(args: ProcessArgs, ctx: ToolContext):
        del ctx
        return svc.process_source(args.source_id, force=args.force)

    def get_job(args: GetJobArgs, ctx: ToolContext):
        del ctx
        return svc.get_job(args.job_id)

    def list_chapters(args: RefArgs, ctx: ToolContext):
        del ctx
        return svc.list_chapters(args.source)

    def read_chapter(args: ReadChapterArgs, ctx: ToolContext):
        del ctx
        return svc.read_chapter(args.source_id, args.chapter, args.offset, args.limit)

    def read_chapter_label(args: dict) -> str:
        """Видео → транскрипт, книга → глава."""
        try:
            kind = svc.get_source(args.get("source_id"))["kind"]
        except Exception:  # noqa: BLE001 — подпись чипа не критична
            return "Читаю главу"
        return "Читаю транскрипт" if kind == "video" else "Читаю главу"

    def research_sources(args: ResearchArgs, ctx: ToolContext):
        del ctx
        return svc.research_sources(args.topic, args.limit)

    return [
        ToolSpec(
            name="add_source",
            module="library",
            description=(
                "Добавить источник в библиотеку. kind: book|video|web; "
                "для video — url, для book — local_path."
            ),
            args_model=SourceCreate,
            handler=add_source,
            label="Добавляю источник",
        ),
        ToolSpec(
            name="list_sources",
            module="library",
            description="Источники библиотеки (фильтр kind).",
            args_model=ListSourcesArgs,
            handler=list_sources,
            label="Источники",
        ),
        ToolSpec(
            name="get_source",
            module="library",
            description="Обзор источника + главы (title, summary, key_points).",
            args_model=RefArgs,
            handler=get_source,
            label="Источник",
        ),
        ToolSpec(
            name="process_source",
            module="library",
            description="Обработать источник: PDF → главы, YouTube → транскрипт. Возвращает job_id.",
            args_model=ProcessArgs,
            handler=process_source,
            label="Обрабатываю источник",
        ),
        ToolSpec(
            name="get_job",
            module="library",
            description="Статус/прогресс job.",
            args_model=GetJobArgs,
            handler=get_job,
            label="Job",
        ),
        ToolSpec(
            name="list_chapters",
            module="library",
            description="Главы обработанного источника.",
            args_model=RefArgs,
            handler=list_chapters,
            label="Главы",
        ),
        ToolSpec(
            name="read_chapter",
            module="library",
            description=(
                "Текст главы порционно: offset/next_offset (листай, пока next_offset не null). "
                "Не грузи весь источник."
            ),
            args_model=ReadChapterArgs,
            handler=read_chapter,
            label=read_chapter_label,
            truncatable=False,
        ),
        ToolSpec(
            name="research_sources",
            module="library",
            description="Веб-поиск источников по теме (кандидаты для add_source).",
            args_model=ResearchArgs,
            handler=research_sources,
            label="Ищу источники",
        ),
    ]
