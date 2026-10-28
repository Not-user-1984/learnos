"""Декларативное описание агента и контекст запуска."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Описание агента и контекст запуска: роль модели, системный промпт, доступные инструменты и лимиты."""

    name: str
    description: str
    prompt_path: Path | None = None  # промпт из файла (дефолтные агенты)
    tools: frozenset[str] = frozenset()
    model_role: str = "chat"
    max_steps: int = 12
    temperature: float | None = None
    output_model: type[BaseModel] | None = None
    prompt_text: str | None = None  # промпт из строки (кастомные агенты из UI)


@dataclass(slots=True)
class AgentContext:
    """Контекст одного запуска агента."""

    system_extra: str = ""  # доп. системный блок «Контекст» (профиль, глава, сессия)
    conversation_uid: str | None = None
    session_uid: str | None = None  # активная сессия разговора: advance работает без явного id
    parent_run_id: int | None = None
    depth: int = 0  # вложенность субагентов: 0 — корневой запуск, ограничена в run_agent
    variables: dict[str, Any] = field(default_factory=dict)  # подстановки Jinja в промпт
    cancellation: "CancellationToken | None" = None


class CancellationToken:
    """Флаг отмены для кнопки «Стоп»."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise AgentCancelled()


class AgentCancelled(Exception):
    """Запуск агента отменён пользователем."""
