"""Спецификация инструмента и контекст вызова."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from ...agent.spec import CancellationToken


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Контекст вызова инструмента: кто и откуда его позвал.

    run_id/depth/cancellation идут от запуска агента — нужны инструменту run_agent,
    чтобы связать трейс субагента с родителем, ограничить вложенность и отдать отмену.
    """

    channel: str = "mcp"  # mcp | agent
    conversation_uid: str | None = None
    session_uid: str | None = None
    agent_name: str | None = None
    run_id: int | None = None
    depth: int = 0
    cancellation: "CancellationToken | None" = None


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
    label: str | Callable[[dict[str, Any]], str] = ""  # подпись чипа; может зависеть от args

    def json_schema(self) -> dict[str, Any]:
        """JSON Schema аргументов для MCP и LLM."""
        return self.args_model.model_json_schema()
