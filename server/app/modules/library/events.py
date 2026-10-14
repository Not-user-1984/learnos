"""Доменные события библиотеки."""

from dataclasses import dataclass

from ...kernel.events import DomainEvent


@dataclass(frozen=True, slots=True)
class SourceProcessed(DomainEvent):
    """Источник обработан: главы готовы."""

    source_uid: str
    source_id: int
    chapters: int
