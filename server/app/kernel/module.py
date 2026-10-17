"""Базовый контракт модуля приложения."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from fastapi import APIRouter

from .tools.spec import ToolSpec

if TYPE_CHECKING:
    from ..bootstrap import Container
    from .events import EventBus


class Module(ABC):
    """Модуль приложения: сам связывает свои зависимости и публикует роуты, инструменты и подписки."""

    name: str

    @abstractmethod
    def wire(self, c: "Container") -> None:
        """Создаёт сервисы модуля и кладёт их в контейнер."""

    def routers(self, c: "Container") -> list[APIRouter]:
        """REST-роуты модуля (монтируются под /api)."""
        return []

    def tools(self, c: "Container") -> list[ToolSpec]:
        """Инструменты модуля для MCP и встроенных агентов."""
        return []

    def subscribe(self, bus: "EventBus", c: "Container") -> None:  # noqa: B027 — пустая подписка допустима
        """Подписки на доменные события других модулей."""
