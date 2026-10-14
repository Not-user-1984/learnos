"""Доменные события обучения."""

from dataclasses import dataclass

from ...kernel.events import DomainEvent


@dataclass(frozen=True, slots=True)
class SessionFinished(DomainEvent):
    """Сессия завершена, блок сохранён."""

    session_uid: str
    block_uid: str


@dataclass(frozen=True, slots=True)
class ActivityProgressed(DomainEvent):
    """Курсор активности сдвинулся (по главе создан блок)."""

    activity_uid: str
    cursor_chapter: int
    total_chapters: int
