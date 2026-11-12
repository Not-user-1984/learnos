"""Провайдер OpenAI-совместимых API (z.ai GLM, OpenAI, OpenRouter, Ollama, vLLM…)."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
import openai

from ...kernel.errors import LLMError
from ..types import LLMEvent, LLMRequest, LLMResponse, ProviderCapabilities, ToolCall, Usage

log = logging.getLogger("learnos.llm.openai_compat")

_RETRYABLE = {"timeout", "unavailable"}
# ошибки, уводящие ключ в cooldown с ротацией на следующий ключ цепочки
_ROTATABLE = {"rate_limit", "auth"}
_ATTEMPTS = 2
_QUOTA_MARKERS = ("quota", "insufficient", "превышен лимит")
# служебные ключи wire-формата — extra-параметры роли их не переопределяют
_RESERVED_WIRE = frozenset({"messages", "tools", "response_format", "stream", "stream_options"})

T = TypeVar("T")


def _normalize_param(key: str, value: Any) -> Any:
    """Привести шорткат параметра к спецификации провайдера.

    GLM допускает thinking только объектом: {'type': 'disabled'}; короткая
    строка из llm.yaml ('disabled') разворачиваем сами (BB-003).
    """
    if key == "thinking" and isinstance(value, str):
        return {"type": value}
    return value


def _map_error(e: Exception) -> LLMError:
    """Перевод исключений SDK в LLMError с кодом."""
    if isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError)):
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
        text = str(e).lower()
        if any(marker in text for marker in _QUOTA_MARKERS):
            return LLMError("превышена квота ключа", code="rate_limit")
        return LLMError(f"провайдер ответил ошибкой {e.status_code}", code="unavailable")
    return LLMError(f"неожиданная ошибка провайдера: {e}", code="unavailable")


class OpenAICompatProvider:
    """Асинхронный клиент /chat/completions с tools, стримингом, ретраями и цепочкой ключей.

    Ключей может быть несколько: при ошибке квоты/авторизации ключ уходит в cooldown
    и запрос повторяется следующим; рабочий индекс sticky. Идентификация ключа
    в логах — только номер (zai#2), значение не логируется.

    httpx-клиент привязан к event loop: при смене петли (воркер с asyncio.run vs uvicorn)
    клиент пересоздаётся, иначе «Event loop is closed».
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        api_keys: list[str],
        capabilities: ProviderCapabilities | None = None,
        *,
        cooldown_seconds: float = 600.0,
        monotonic: Callable[[], float] = time.monotonic,
        proxy_from: Callable[[], str] | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities or ProviderCapabilities()
        self._base_url = base_url
        self._api_keys = api_keys
        self._cooldown_seconds = cooldown_seconds
        self._monotonic = monotonic
        self._sticky = 0
        self._cooldown_until: dict[int, float] = {}
        self._clients: dict[int | None, openai.AsyncOpenAI] = {}
        self._loop_id: int | None = None
        # прокси провайдера (B-011): OpenAI блокирует регион прода — роль embed ходит
        # через socks5 из настроек связи (UI); пустая строка = напрямую
        self._proxy_from = proxy_from
        self._proxy_stamp: str | None = None
        # extra-параметры ролей, отвергнутые провайдером (bad_request) — не шлём до перезапуска
        self._unsupported_extra: set[str] = set()

    # --- цепочка ключей ---

    def _pick_key(self) -> int | None:
        """Индекс рабочего ключа: sticky, по кругу, пропуская cooldown.

        None — провайдер без ключей (keyless). LLMError, если все ключи в cooldown.
        """
        n = len(self._api_keys)
        if n == 0:
            return None
        now = self._monotonic()
        for step in range(n):
            idx = (self._sticky + step) % n
            until = self._cooldown_until.get(idx)
            if until is not None and until > now:
                continue
            if until is not None:
                del self._cooldown_until[idx]  # cooldown истёк — ключ снова в строю
            self._sticky = idx
            return idx
        reset = min(self._cooldown_until.values())
        minutes = max(1, round((reset - now) / 60))
        raise LLMError(
            f"все ключи провайдера {self.name} ({n} шт.) в cooldown после ошибок квоты; "
            f"ближайший сброс примерно через {minutes} мин",
            code="rate_limit",
        )

    def _cooldown_key(self, idx: int) -> None:
        self._cooldown_until[idx] = self._monotonic() + self._cooldown_seconds
        log.warning(
            "ключ %s#%d в cooldown на %d с после ошибки квоты/авторизации",
            self.name,
            idx + 1,
            int(self._cooldown_seconds),
        )

    def keychain_status(self) -> dict[str, Any]:
        """Состояние цепочки ключей: sticky-индекс и cooldown-остатки (BB-004).

        Ключи идентифицируются только номером; значения не отдаём нигде.
        """
        now = self._monotonic()
        keys: list[dict[str, Any]] = []
        for i in range(len(self._api_keys)):
            until = self._cooldown_until.get(i)
            remain = int(round(until - now)) if until is not None and until > now else 0
            if remain > 0:
                keys.append({"index": i + 1, "state": "cooldown", "cooldown_seconds": remain})
            elif i == self._sticky:
                keys.append({"index": i + 1, "state": "active"})
            else:
                keys.append({"index": i + 1, "state": "ready"})
        return {
            "keys_total": len(self._api_keys),
            "sticky": (self._sticky + 1) if self._api_keys else None,
            "keys": keys,
        }

    def reset_cooldown(self) -> int:
        """Сбросить cooldown всех ключей (ручное «переключение ключа», BB-005).

        Безопасно: просто очищает карту — следующий запрос берёт первый
        свободный ключ цепочки. Возвращает число снятых cooldown.
        """
        dropped = len(self._cooldown_until)
        self._cooldown_until.clear()
        if dropped:
            log.info("провайдер %s: cooldown снят у %d ключей", self.name, dropped)
        return dropped

    async def _with_key_rotation(self, attempt: Callable[[int | None], Awaitable[T]]) -> T:
        """Выполнить запрос текущим ключом; при ошибке квоты — cooldown и следующий ключ."""
        while True:
            idx = self._pick_key()
            try:
                return await attempt(idx)
            except LLMError as err:
                if idx is None or err.code not in _ROTATABLE:
                    raise
                self._cooldown_key(idx)

    # --- клиент ---

    def _current_proxy(self) -> str:
        """Текущий прокси провайдера (пусто — напрямую). Читается при каждом запросе:
        смена настроек связи в UI подхватывается без рестарта."""
        if self._proxy_from is None:
            return ""
        return (self._proxy_from() or "").strip()

    def _make_client(self, api_key: str | None) -> openai.AsyncOpenAI:
        proxy = self._current_proxy()
        if proxy:
            return openai.AsyncOpenAI(
                base_url=self._base_url,
                api_key=api_key or "not-set",
                timeout=120.0,
                max_retries=0,
                http_client=httpx.AsyncClient(proxy=proxy),
            )
        return openai.AsyncOpenAI(
            base_url=self._base_url, api_key=api_key or "not-set", timeout=120.0, max_retries=0
        )

    def _ensure_client(self, key_index: int | None) -> openai.AsyncOpenAI:
        import asyncio

        loop = asyncio.get_running_loop()
        if self._loop_id != id(loop):
            self._loop_id = id(loop)
            self._clients = {}
        proxy = self._current_proxy()
        if proxy != self._proxy_stamp:
            # сменился прокси (настройки связи из UI) — клиенты пересобираются
            self._proxy_stamp = proxy
            self._clients = {}
        client = self._clients.get(key_index)
        if client is None:
            api_key = self._api_keys[key_index] if key_index is not None else None
            client = self._make_client(api_key)
            self._clients[key_index] = client
        return client

    def _to_wire(self, request: LLMRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        """Собрать wire-запрос; возвращает (payload, extra-параметры роли).

        extra-параметры из llm.yaml (BB-003) идут отдельным словарём — SDK не
        принимает чужие kwargs, они уходят в тело запроса через extra_body.
        Отдаются только если заданы конфигом, не дублируют явные поля запроса
        (temperature/max_tokens) и не переопределяют служебные ключи wire-формата.
        """
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
        extra: dict[str, Any] = {}
        for key, value in (request.extra_params or {}).items():
            if key in self._unsupported_extra or key in _RESERVED_WIRE:
                continue
            if key == "temperature" and request.temperature is not None:
                continue  # явное поле запроса приоритетнее params роли
            if key == "max_tokens" and request.max_tokens is not None:
                continue
            extra[key] = _normalize_param(key, value)
        return payload, extra

    def _drop_extra(self, extra: dict[str, Any]) -> None:
        """Запомнить extra-параметры как отвергнутые провайдером и убрать из запроса.

        Вызывается после bad_request: параметр роли не должен зацикливать
        ретраи — после снятия он больше не собирается в wire до перезапуска.
        """
        self._unsupported_extra.update(extra)
        names = list(extra)
        extra.clear()  # мутация: замыкание ротации видит дроп на всех ключах
        log.warning(
            "провайдер %s отверг параметры роли (%s) — убраны из запроса",
            self.name,
            ", ".join(names),
        )

    async def complete(self, model: str, request: LLMRequest) -> LLMResponse:
        """Один ответ целиком: ротация ключей по квоте + ретраи временных ошибок."""
        payload, extra = self._to_wire(request)
        return await self._with_key_rotation(lambda idx: self._complete_attempts(model, payload, extra, idx))

    async def _complete_attempts(
        self, model: str, payload: dict[str, Any], extra: dict[str, Any], key_index: int | None
    ) -> LLMResponse:
        attempt = 0
        while True:
            try:
                call = {**payload, **({"extra_body": dict(extra)} if extra else {})}
                resp = await self._ensure_client(key_index).chat.completions.create(model=model, **call)
                return self._parse_response(resp)
            except Exception as e:  # noqa: BLE001 — граница к внешнему сервису
                err = _map_error(e)
                # bad_request тоже ретраим: z.ai иногда отвечает плавающим 1214 на валидный запрос.
                # Если в запросе есть extra-параметры роли — сначала пробуем без них (BB-003)
                if err.code == "bad_request" and extra:
                    self._drop_extra(extra)
                    continue
                if (err.code in _RETRYABLE or err.code == "bad_request") and attempt < _ATTEMPTS - 1:
                    attempt += 1
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise err from e

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Эмбеддинги батча текстов через /embeddings (B-008): ротация ключей + ретраи."""
        payload = {"model": model, "input": list(texts)}
        return await self._with_key_rotation(lambda idx: self._embed_attempts(model, payload, idx))

    async def _embed_attempts(
        self, model: str, payload: dict[str, Any], key_index: int | None
    ) -> list[list[float]]:
        attempt = 0
        while True:
            try:
                resp = await self._ensure_client(key_index).embeddings.create(**payload)
                return [list(d.embedding) for d in resp.data]
            except Exception as e:  # noqa: BLE001 — граница к внешнему сервису
                err = _map_error(e)
                if err.code in _RETRYABLE and attempt < _ATTEMPTS - 1:
                    attempt += 1
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise err from e

    def stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Стриминговый ответ; tool calls собираются и отдаются целиком в конце текста."""
        return self._stream(model, request)

    async def _stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        payload, extra = self._to_wire(request)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        stream = await self._with_key_rotation(lambda idx: self._open_stream(model, payload, extra, idx))
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
                    # ключ — index (R-23): у OpenAI-совместимых id приходит только в первом
                    # чанке, дельты аргументов — с index; старый ключ "id or index" расползался
                    # на два слота и рождал «призрачные» tool-call'ы с пустым именем
                    key = tc.index if tc.index is not None else (tc.id or 0)
                    slot = collected.setdefault(key, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["args"] += tc.function.arguments
        for i, slot in enumerate(collected.values()):
            if not slot["id"]:
                slot["id"] = f"call_{slot['name'] or 'tool'}_{i}"  # без коллизий одноимённых (R-23)
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

    async def _open_stream(
        self, model: str, payload: dict[str, Any], extra: dict[str, Any], key_index: int | None
    ) -> Any:
        """Открыть стрим с ретраями временных ошибок (квота уходит в ротацию выше).

        bad_request с extra-параметрами роли — сначала ретрай без них (BB-003).
        """
        attempt = 0
        while True:
            try:
                call = {**payload, **({"extra_body": dict(extra)} if extra else {})}
                return await self._ensure_client(key_index).chat.completions.create(model=model, **call)
            except Exception as e:  # noqa: BLE001
                err = _map_error(e)
                if err.code == "bad_request":
                    _dump_1214(model, payload, str(e))
                    if extra:
                        self._drop_extra(extra)
                        continue
                if (err.code in _RETRYABLE or err.code == "bad_request") and attempt < _ATTEMPTS - 1:
                    attempt += 1
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise err from e

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
