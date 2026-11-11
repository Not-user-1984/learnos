"""Доменные события курсов."""

from dataclasses import dataclass

from ...kernel.events import DomainEvent


@dataclass(frozen=True, slots=True)
class CourseItemStatusChanged(DomainEvent):
    """Элемент курса сменил статус (todo|doing|read|done) — доска обновилась."""

    course_id: int
    item_id: int
    status: str
