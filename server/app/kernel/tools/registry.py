"""ToolRegistry: сбор всех инструментов, вызов с валидацией, обрезка результатов для LLM."""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from ..errors import AppError
from .spec import ToolContext, ToolSpec

log = logging.getLogger("learnos.tools")


class UnknownTool(AppError):
    """Инструмент с таким именем не зарегистрирован."""

    code = "unknown_tool"
    http_status = 404


class DuplicateTool(AppError):
    """Имя инструмента должно быть уникально глобально."""

    code = "duplicate_tool"
    http_status = 500


class ToolRegistry:
    """Все инструменты приложения; строит MCP-серверы и описания для агентов."""

    def __init__(self, max_result_chars: int = 8000) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._max_result_chars = max_result_chars

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise DuplicateTool(f"инструмент '{spec.name}' уже зарегистрирован")
        self._tools[spec.name] = spec

    def has(self, name: str) -> bool:
        return name in self._tools

    def unregister(self, name: str) -> None:
        """Снять инструмент (динамические обёртки внешних MCP)."""
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolSpec:
        spec = self._tools.get(name)
        if spec is None:
            raise UnknownTool(f"инструмент '{name}' не найден")
        return spec

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def by_module(self, module: str) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.module == module]

    def filter(
        self,
        *,
        names: set[str] | None = None,
        module: str | None = None,
        channel: str | None = None,
        mode: str | None = None,
    ) -> list[ToolSpec]:
        """Отбор инструментов для конкретного потребителя (агент, MCP-модуль)."""
        out = []
        for t in self._tools.values():
            if names is not None and t.name not in names:
                continue
            if module is not None and t.module != module:
                continue
            if channel is not None and channel not in t.channels:
                continue
            if mode is not None and mode not in t.modes:
                continue
            out.append(t)
        return out

    def call(self, name: str, raw_args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Вызвать инструмент: валидация аргументов, AppError → {"error", "message"}, обрезка для агента."""
        spec = self.get(name)
        try:
            args = spec.args_model.model_validate(raw_args)
        except ValidationError as e:
            return {
                "error": "validation_failed",
                "message": e.errors(include_url=False)[0]["msg"] if e.errors() else "bad args",
            }
        try:
            result = spec.handler(args, ctx)
            if isinstance(result, BaseModel):
                result = result.model_dump(mode="json")
        except AppError as e:
            return {"error": e.code, "message": e.message}
        payload = _to_jsonable(result)
        if ctx.channel == "agent":
            if not isinstance(payload, dict):
                # списки оборачиваем для агента: дальше словарь (обрезка, _card); MCP отдаёт как есть
                payload = {"result": payload}
            payload = _truncate(payload, self._max_result_chars)
        return payload


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _truncate(payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Обрезка длинных строковых полей результата, чтобы не раздувать контекст LLM."""
    card = payload.pop("_card", None)
    text = str(payload)
    if len(text) <= max_chars:
        if card is not None:
            payload["_card"] = card
        return payload
    trimmed = {
        k: (v[: max_chars // 2] + "…" if isinstance(v, str) and len(v) > max_chars // 2 else v)
        for k, v in payload.items()
        if not isinstance(v, (list, dict)) or len(str(v)) < max_chars // 2
    }
    trimmed["truncated"] = True
    if card is not None:
        trimmed["_card"] = card
    return trimmed
