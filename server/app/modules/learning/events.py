"""Доменные события обучения."""

from dataclasses import dataclass

from ...kernel.events import DomainEvent


@dataclass(frozen=True, slots=True)
class SessionStarted(DomainEvent):
    """Сессия начата (курсы переводят элемент в doing)."""

    session_uid: str
    course_id: int | None = None
    course_item_id: int | None = None
    activity_uid: str | None = None
    source_uid: str | None = None
    chapter_idx: int | None = None


@dataclass(frozen=True, slots=True)
class SessionFinished(DomainEvent):
    """Сессия завершена, блок сохранён.

    Курсы закрывают элемент (по course_item_id или паре источник/глава во всех
    курсах), повторения заводят review_item — learning никого не зовёт сам.
    """

    session_uid: str
    block_uid: str
    course_id: int | None = None
    course_item_id: int | None = None
    activity_uid: str | None = None
    source_uid: str | None = None
    chapter_idx: int | None = None


@dataclass(frozen=True, slots=True)
class ChapterRead(DomainEvent):
    """Глава прочитана/разобрана без сессии-урока («прочитал сам», quick-разбор)."""

    activity_uid: str
    source_uid: str
    chapter_idx: int
    course_id: int | None = None


@dataclass(frozen=True, slots=True)
class ActivityProgressed(DomainEvent):
    """Курсор активности сдвинулся (по главе создан блок)."""

    activity_uid: str
    cursor_chapter: int
    total_chapters: int
