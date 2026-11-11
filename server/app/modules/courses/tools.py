"""Инструменты модуля courses (MCP + агенты)."""

import json

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class CreateCourseArgs(BaseModel):
    """create_course: совместимость со старым topic+plan_json + новый формат."""

    topic: str = Field(description="Тема курса")
    title: str | None = Field(default=None, description="Заголовок (по умолчанию тема)")
    description: str | None = Field(default=None, description="Описание")
    plan_json: str = Field(default="{}", description="Старый формат: план JSON-строкой")
    items: list[dict] = Field(
        default_factory=list, description="Элементы: [{item_type, source, chapter, block_uid}]"
    )


class RefArgs(BaseModel):
    """Ссылка на курс (uid или id)."""

    course_id: str | int = Field(description="uid/id курса")


class CourseItemArgs(BaseModel):
    """add_course_item: элемент + курс."""

    course_id: str | int = Field(description="uid/id курса")
    item_type: str = Field(description="source | chapter | block")
    source: str | int | None = Field(default=None, description="uid/id источника (для source/chapter)")
    chapter: int | None = Field(default=None, description="Номер главы (для chapter)")
    block_uid: str | None = Field(default=None, description="uid блока (для block)")
    note: str | None = Field(default=None, description="Заметка к элементу")


class RemoveItemArgs(BaseModel):
    """remove_course_item."""

    course_id: str | int = Field(description="uid/id курса")
    item_id: int = Field(description="id элемента")


class ReorderArgs(BaseModel):
    """reorder_course: новый порядок id элементов."""

    course_id: str | int = Field(description="uid/id курса")
    item_ids: list[int] = Field(description="id элементов в новом порядке")


class NoArgs(BaseModel):
    """Без аргументов."""


def courses_tools(c) -> list[ToolSpec]:
    """Инструменты курсов."""
    svc = c.courses

    def create_course(args: CreateCourseArgs, ctx: ToolContext):
        del ctx
        plan = json.loads(args.plan_json) if args.plan_json and args.plan_json != "{}" else None
        return svc.create_course(
            args.topic, args.title or args.topic, args.description, items=args.items, plan=plan
        )

    def list_courses(args: NoArgs, ctx: ToolContext):
        del ctx, args
        return svc.list_courses()

    def get_course(args: RefArgs, ctx: ToolContext):
        del ctx
        return svc.get_course(args.course_id)

    def add_course_item(args: CourseItemArgs, ctx: ToolContext):
        del ctx
        return svc.add_item(
            args.course_id, args.item_type, args.source, args.chapter, args.block_uid, args.note
        )

    def remove_course_item(args: RemoveItemArgs, ctx: ToolContext):
        del ctx
        return svc.remove_item(args.course_id, args.item_id)

    def reorder_course(args: ReorderArgs, ctx: ToolContext):
        del ctx
        return svc.reorder(args.course_id, args.item_ids)

    return [
        ToolSpec(
            name="create_course",
            module="courses",
            description=(
                "Создать курс по теме. Опционально items: "
                "[{item_type: source|chapter|block, source, chapter, block_uid, note}]."
            ),
            args_model=CreateCourseArgs,
            handler=create_course,
            label="Создаю курс",
        ),
        ToolSpec(
            name="list_courses",
            module="courses",
            description="Курсы с прогрессом.",
            args_model=NoArgs,
            handler=list_courses,
            label="Курсы",
        ),
        ToolSpec(
            name="get_course",
            module="courses",
            description="Курс с элементами, прогрессом и следующим шагом.",
            args_model=RefArgs,
            handler=get_course,
            label="Курс",
        ),
        ToolSpec(
            name="add_course_item",
            module="courses",
            description="Добавить элемент курса (source | chapter | block).",
            args_model=CourseItemArgs,
            handler=add_course_item,
            label="Добавляю в курс",
        ),
        ToolSpec(
            name="remove_course_item",
            module="courses",
            description="Удалить элемент курса.",
            args_model=RemoveItemArgs,
            handler=remove_course_item,
            label="Удаляю из курса",
        ),
        ToolSpec(
            name="reorder_course",
            module="courses",
            description="Переставить элементы курса (список item_id в новом порядке).",
            args_model=ReorderArgs,
            handler=reorder_course,
            label="Порядок курса",
        ),
    ]
