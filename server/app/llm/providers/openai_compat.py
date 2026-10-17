"""Провайдер OpenAI-совместимых API (z.ai GLM, OpenAI, OpenRouter, Ollama, vLLM…)."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import openai

from ...kernel.errors import LLMError
from ..types import LLMEvent, LLMRequest, LLMResponse, ProviderCapabilities, ToolCall, Usage

log = logging.getLogger("learnos.llm.openai_compat")

_RETRYABLE = {"rate_limit", "timeout", "unavailable"}
_ATTEMPTS = 2


def _map_error(e: Exception) -> LLMError:
    """Перевод исключений SDK в LLMError с кодом."""
    if isinstance(e, openai.AuthenticationError):
        return LLMError("ключ API не принят провайдером", code="auth")
    if isinstance(e, openai.RateLimitError):
        return LLMError("превышен лимит запросов", code="rate_limit")
    if isinstance(e, (openai.APITimeoutError, asyncio.TimeoutError)):
        return LLMError("таймаут запроса к модели", code="timeout")
    if isinstance(e, openai.BadRequestError):
        return LLMError(f"провайдер отклонил запрос: {e}", code="bad_request")
    if isinstance(e, openai.APIConnectionError):
        return LLMError("провайдер недоступен", code="unavailable")
    if isinstance(e, openai.APIStatusError):
        return LLMError(f"провайдер ответил ошибкой {e.status_code}", code="unavailable")
    return LLMError(f"неожиданная ошибка провайдера: {e}", code="unavailable")


class OpenAICompatProvider:
    """Асинхронный клиент /chat/completions с tools, стримингом и ретраями.

    httpx-клиент привязан к event loop: при смене петли (воркер с asyncio.run vs uvicorn)
    клиент пересоздаётся, иначе «Event loop is closed».
    """

    def __init__(
        self, name: str, base_url: str, api_key: str | None, capabilities: ProviderCapabilities | None = None
    ) -> None:
        self.name = name
        self.capabilities = capabilities or ProviderCapabilities()
        self._base_url = base_url
        self._api_key = api_key
        self._client: openai.AsyncOpenAI | None = None
        self._loop_id: int | None = None

    def _ensure_client(self) -> openai.AsyncOpenAI:
        import asyncio

        loop = asyncio.get_running_loop()
        if self._client is None or self._loop_id != id(loop):
            self._loop_id = id(loop)
            self._client = openai.AsyncOpenAI(
                base_url=self._base_url, api_key=self._api_key or "not-set", timeout=120.0, max_retries=0
            )
        return self._client

    def _to_wire(self, request: LLMRequest) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for m in request.messages:
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.role == "assistant" and m.tool_calls:
                # z.ai требует content=null (не пустую строку) при tool_calls
                entry = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, ensure_ascii=False),
                            },
                        }
                        for c in m.tool_calls
                    ],
                }
            if m.role == "tool":
                entry = {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
            messages.append(entry)
        payload: dict[str, Any] = {"messages": messages}
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in request.tools
            ]
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_schema is not None and self.capabilities.json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": request.response_schema},
            }
        elif request.response_schema is not None:
            # z.ai не поддерживает json_schema — схему добавляем в системное сообщение, валидируем сами
            schema_json = json.dumps(request.response_schema, ensure_ascii=False)
            payload["messages"] = [
                {"role": "system", "content": f"Отвечай ТОЛЬКО валидным JSON по схеме:\n{schema_json}"}
            ] + messages
        return payload

    async def complete(self, model: str, request: LLMRequest) -> LLMResponse:
        """Один ответ целиком с ретраем для временных ошибок."""
        payload = self._to_wire(request)
        last_error: LLMError | None = None
        for attempt in range(_ATTEMPTS):
            try:
                resp = await self._ensure_client().chat.completions.create(model=model, **payload)
                return self._parse_response(resp)
            except Exception as e:  # noqa: BLE001 — граница к внешнему сервису
                err = _map_error(e)
                # bad_request тоже ретраим: z.ai иногда отвечает плавающим 1214 на валидный запрос
                if (err.code in _RETRYABLE or err.code == "bad_request") and attempt < _ATTEMPTS - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                last_error = err
                raise last_error from e
        raise last_error or LLMError("нет ответа провайдера")

    def stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Стриминговый ответ; tool calls собираются и отдаются целиком в конце текста."""
        return self._stream(model, request)

    async def _stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        payload = self._to_wire(request)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        stream = None
        for attempt in range(_ATTEMPTS):
            try:
                stream = await self._ensure_client().chat.completions.create(model=model, **payload)
                break
            except Exception as e:  # noqa: BLE001
                err = _map_error(e)
                if err.code == "bad_request":
                    _dump_1214(model, payload, str(e))
                if (err.code in _RETRYABLE or err.code == "bad_request") and attempt < _ATTEMPTS - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise err from e
        if stream is None:
            raise LLMError("нет ответа провайдера")

        collected: dict[str, dict[str, Any]] = {}
        usage: Usage | None = None
        finish = ""
        async for chunk in stream:
            if chunk.usage:
                usage = Usage(
                    input_tokens=chunk.usage.prompt_tokens or 0,
                    output_tokens=chunk.usage.completion_tokens or 0,
                )
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish = choice.finish_reason
            delta = choice.delta
            if delta and delta.content:
                yield LLMEvent(type="text", text=delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = collected.setdefault(tc.id or tc.index, {"id": "", "name": "", "args": ""})  # type: ignore[assignment]
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["args"] += tc.function.arguments
        for slot in collected.values():
            if not slot["id"]:
                slot["id"] = f"call_{slot['name']}"
            try:
                arguments = json.loads(slot["args"]) if slot["args"] else {}
            except json.JSONDecodeError:
                arguments = {"_raw": slot["args"]}
            yield LLMEvent(
                type="tool_call", tool_call=ToolCall(id=slot["id"], name=slot["name"], arguments=arguments)
            )
        if usage:
            yield LLMEvent(type="usage", usage=usage)
        yield LLMEvent(type="finish", finish_reason=finish or "stop")

    @staticmethod
    def _parse_response(resp: Any) -> LLMResponse:
        choice = resp.choices[0]
        msg = choice.message
        calls = tuple(
            ToolCall(
                id=tc.id or f"call_{i}",
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments) if tc.function.arguments else {},
            )
            for i, tc in enumerate(msg.tool_calls or [])
        )
        usage = (
            Usage(input_tokens=resp.usage.prompt_tokens, output_tokens=resp.usage.completion_tokens)
            if resp.usage
            else None
        )
        return LLMResponse(
            text=msg.content or "",
            tool_calls=calls,
            usage=usage,
            finish_reason=choice.finish_reason or "stop",
        )


def _dump_1214(model: str, payload: dict[str, Any], error: str) -> None:
    """Сохранить провалившийся запрос для диагностики плавающих 1214 (без ключа, ключа тут и нет)."""
    import os
    import time

    try:
        path = os.environ.get("LEARNOS_DATA_DIR", "/data")
        name = f"{path}/err_1214_{int(time.time())}.json"
        with open(name, "w", encoding="utf-8") as f:
            json.dump(
                {"model": model, "error": error[:300], "payload": payload}, f, ensure_ascii=False, indent=1
            )
    except OSError:
        pass
