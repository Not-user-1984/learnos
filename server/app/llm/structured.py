"""Структурированный вывод: просим JSON по pydantic-схеме, валидируем, до 2 повторов с ошибкой."""

import json
import logging
import re

from pydantic import BaseModel, ValidationError

from ..kernel.errors import LLMError
from .provider import LLMProvider
from .types import LLMRequest, Message

log = logging.getLogger("learnos.llm.structured")

_MAX_ATTEMPTS = 3


async def structured_output(
    provider: LLMProvider,
    model: str,
    messages: list[Message],
    output: type[BaseModel],
    *,
    temperature: float | None = None,
) -> BaseModel:
    """Гарантированно получить экземпляр pydantic-модели от LLM (до 2 повторов при невалидном JSON)."""
    schema = output.model_json_schema()
    attempt_messages = list(messages)
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        request = LLMRequest(
            messages=tuple(attempt_messages),
            response_schema=schema,
            temperature=temperature,
        )
        response = await provider.complete(model, request)
        try:
            return output.model_validate_json(_extract_json(response.text))
        except ValidationError as e:
            last_error = e
            log.warning("structured attempt %d invalid: %s", attempt, e.error_count())
            attempt_messages = attempt_messages + [
                Message(role="assistant", content=response.text),
                Message(
                    role="user",
                    content=(
                        f"JSON невалиден: {e.errors(include_url=False)[:3]}. "
                        "Ответь ТОЛЬКО валидным JSON по схеме."
                    ),
                ),
            ]
    raise LLMError(f"модель не выдала валидную структуру после {_MAX_ATTEMPTS} попыток: {last_error}")


def _extract_json(text: str) -> str:
    """Достать JSON из ответа модели (убрать ```-заборы и текст вокруг)."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        candidate = candidate[start : end + 1]
    return candidate.strip() or json.dumps({})
