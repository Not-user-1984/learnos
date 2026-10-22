"""Доменные события базы знаний."""

from dataclasses import dataclass

from ...kernel.events import DomainEvent


@dataclass(frozen=True, slots=True)
class BlockSaved(DomainEvent):
    """Блок записан в KB (файл + индекс)."""

    block_uid: str
    kind: str
    title: str
    category_path: str | None = None


@dataclass(frozen=True, slots=True)
class BlockUpdated(DomainEvent):
    """Блок отредактирован (версия выросла)."""

    block_uid: str
    version: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BlockDeleted(DomainEvent):
    """Блок удалён (вместе с версиями, файлом и поисковой строкой)."""

    block_uid: str


@dataclass(frozen=True, slots=True)
class CategoryConfirmed(DomainEvent):
    """Пользователь подтвердил категорию блока."""

    block_uid: str
    path: str
