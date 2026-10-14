"""DTO курсов."""

from pydantic import BaseModel


class CourseCreate(BaseModel):
    """Создание курса."""

    title: str | None = None
    topic: str
    description: str | None = None
    category: str | None = None
    items: list[dict] = []


class CoursePatch(BaseModel):
    """Правка курса."""

    title: str | None = None
    description: str | None = None
    status: str | None = None


class CourseItemIn(BaseModel):
    """Элемент курса."""

    item_type: str  # source | chapter | block
    source: str | int | None = None
    chapter: int | None = None
    block_uid: str | None = None
    note: str | None = None


class ReorderIn(BaseModel):
    """Новый порядок элементов."""

    item_ids: list[int]
