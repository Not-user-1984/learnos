"""Нейтральные типы диалога с моделью — не привязаны к API конкретного провайдера."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Вызов инструмента, запрошенный моделью."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Message:
    """Сообщение диалога в нейтральном формате."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """Описание инструмента для модели: имя, описание, JSON Schema аргументов."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Запрос к модели; провайдер переводит его в свой формат."""

    messages: tuple[Message, ...]
    tools: tuple[ToolSchema, ...] = ()
    temperature: float | None = None
    max_tokens: int | None = None
    response_schema: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    """Расход токенов одного вызова."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Итог нестримингового вызова."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage | None = None
    finish_reason: str = "stop"


# --- Потоковые события провайдера ---

EventType = Literal["text", "tool_call", "usage", "finish"]


@dataclass(frozen=True, slots=True)
class LLMEvent:
    """Одно событие стрима: text | tool_call | usage | finish."""

    type: EventType
    text: str = ""
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    finish_reason: str = ""


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Что умеет провайдер; от этого зависит поведение structured_output и стриминга."""

    tools: bool = True
    streaming: bool = True
    json_schema: bool = False
    vision: bool = False
