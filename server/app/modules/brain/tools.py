"""Инструменты «второго мозга» (B-007): компактный набор для внешних нейронок.

/mcp/brain — 8 тулов: положить (capture/add_source), получить контекст
(context/search/get/list_topics), разобрать входящие (inbox/promote_hint).
"""

from typing import Literal

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class CaptureArgs(BaseModel):
    """Положить материал в LearnOS за один вызов (идемпотентно)."""

    kind: Literal["text", "url"] = Field(
        description="text — заметка во входящие; url — источник в библиотеку"
    )
    content: str = Field(min_length=2, description="Текст заметки или ссылка (YouTube/PDF/статья)")
    title: str | None = Field(default=None, max_length=100, description="Заголовок (для заметки)")
    topic: str | None = Field(default=None, description="Категория-категория, например infra/kubernetes")
    tags: list[str] = Field(default_factory=list, max_length=5, description="Теги заметки")
    source_agent: str | None = Field(default=None, description="Имя нейронки, которая кладёт (для метки)")


class ContextArgs(BaseModel):
    """Контекст по теме за один вызов."""

    topic: str = Field(min_length=2, description="Тема/вопрос: по нему ищем блоки, главы и входящие")
    budget_chars: int = Field(default=8000, ge=500, le=30000, description="Лимит символов ответа")
    include: list[Literal["blocks", "chapters", "inbox"]] = Field(
        default_factory=lambda: ["blocks", "chapters", "inbox"], description="Что включать в контекст"
    )
    cursor: int = Field(default=0, ge=0, description="Смещение (next_cursor прошлого запроса)")


class GetArgs(BaseModel):
    """Пачка материалов по uid из context/search."""

    uids: list[str] = Field(min_length=1, max_length=10, description="uid: blk_…, src_… или глава src_…:N")
    max_chars_each: int = Field(default=4000, ge=200, le=20000, description="Лимит символов на материал")


class SearchKbArgs(BaseModel):
    """Полнотекстовый поиск (FTS5) по блокам и главам."""

    query: str = Field(min_length=2, description="Поисковый запрос")
    limit: int = Field(default=10, ge=1, le=30, description="Сколько результатов")


class ListTopicsArgs(BaseModel):
    """Без аргументов."""


class AddSourceKbArgs(BaseModel):
    """Источник в библиотеку (дедуп по URL)."""

    kind: Literal["book", "video", "web", "article"] = Field(description="Тип источника")
    title: str = Field(min_length=2, description="Название")
    url: str | None = Field(default=None, description="Ссылка (дедуп по ней же)")


class InboxArgs(BaseModel):
    """Входящие базы знаний: сырьё, ждущее сессии."""

    limit: int = Field(default=20, ge=1, le=100, description="Сколько записей")


class PromoteHintArgs(BaseModel):
    """Подсказка, как сделать блок выученным."""

    uid: str = Field(description="uid блока (blk_…)")


def brain_tools(c) -> list[ToolSpec]:
    """Инструменты второго мозга: capture → context → get."""
    svc = c.brain

    def capture(args: CaptureArgs, ctx: ToolContext):
        del ctx
        return svc.capture(args.kind, args.content, args.title, args.topic, args.tags, args.source_agent)

    def context(args: ContextArgs, ctx: ToolContext):
        del ctx
        return svc.context(args.topic, args.budget_chars, args.include, args.cursor)

    def get(args: GetArgs, ctx: ToolContext):
        del ctx
        return svc.get(args.uids, args.max_chars_each)

    def search_kb(args: SearchKbArgs, ctx: ToolContext):
        del ctx
        out = svc.context(args.query, budget_chars=12000, cursor=0)
        return {
            "query": args.query,
            "items": [i for i in out["items"] if i["type"] != "inbox"][: args.limit],
        }

    def list_topics(args: ListTopicsArgs, ctx: ToolContext):
        del args, ctx
        return svc.list_topics()

    def add_source_kb(args: AddSourceKbArgs, ctx: ToolContext):
        del ctx
        return svc.add_source(args.kind, args.title, args.url)

    def inbox(args: InboxArgs, ctx: ToolContext):
        del ctx
        return svc.inbox(args.limit)

    def promote_hint(args: PromoteHintArgs, ctx: ToolContext):
        del ctx
        return svc.promote_hint(args.uid)

    return [
        ToolSpec(
            name="capture",
            module="brain",
            description=(
                "Положить материал в LearnOS за один вызов, идемпотентно (повтор — created=false). "
                "text → заметка во входящие (не выученное!); url → источник в библиотеку + обработка."
            ),
            args_model=CaptureArgs,
            handler=capture,
            label="Capture",
        ),
        ToolSpec(
            name="context",
            module="brain",
            description=(
                "Компактный контекст по теме за один вызов: verified-блоки → главы книг → входящие, "
                "в пределах budget_chars. Каждый элемент несёт uid для get()."
            ),
            args_model=ContextArgs,
            handler=context,
            label="Контекст по теме",
        ),
        ToolSpec(
            name="search_kb",
            module="brain",
            description="FTS-поиск по базе знаний и главам: uid + сниппеты (короткий вариант context).",
            args_model=SearchKbArgs,
            handler=search_kb,
            label="Поиск",
        ),
        ToolSpec(
            name="get",
            module="brain",
            description=(
                "Материалы пачкой по uid: блок blk_…, источник src_…, глава src_…:N "
                "(uid приходят из context/search)."
            ),
            args_model=GetArgs,
            handler=get,
            label="Читаю материалы",
        ),
        ToolSpec(
            name="list_topics",
            module="brain",
            description="Дерево категорий базы знаний с числом блоков.",
            args_model=ListTopicsArgs,
            handler=list_topics,
            label="Категории",
        ),
        ToolSpec(
            name="add_source_kb",
            module="brain",
            description="Добавить источник в библиотеку (дедуп по URL); обработку запустит capture(url).",
            args_model=AddSourceKbArgs,
            handler=add_source_kb,
            label="Источник",
        ),
        ToolSpec(
            name="inbox",
            module="brain",
            description="Входящие базы знаний: заметки нейронок и человека, ждут сессии-проговора.",
            args_model=InboxArgs,
            handler=inbox,
            label="Входящие",
        ),
        ToolSpec(
            name="promote_hint",
            module="brain",
            description=(
                "Как превратить блок в выученный: НЕ флагом — только сессия-урок "
                "(правило LearnOS: verified = проговорено)."
            ),
            args_model=PromoteHintArgs,
            handler=promote_hint,
            label="Как выучить",
        ),
    ]
