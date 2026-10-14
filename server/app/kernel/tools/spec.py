"""Спецификация инструмента и контекст вызова."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Контекст вызова инструмента: кто и откуда его позвал."""

    channel: str = "mcp"  # mcp | agent
    conversation_uid: str | None = None
    session_uid: str | None = None
    agent_name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Описание инструмента: имя, pydantic-схема аргументов, обработчик, каналы и режимы."""

    name: str
    module: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], Any]
    channels: frozenset[str] = field(default=frozenset({"mcp", "agent"}))
    modes: frozenset[str] = field(default=frozenset({"free", "quick", "session"}))
    label: str = ""  # человекочитаемая подпись для чипа в чате

    def json_schema(self) -> dict[str, Any]:
        """JSON Schema аргументов для MCP и LLM."""
        return self.args_model.model_json_schema()
