"""Фейковый провайдер для тестов: сценарий ответов, запись запросов."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ..types import LLMEvent, LLMRequest, LLMResponse, ProviderCapabilities, ToolCall, Usage


class FakeTurn:
    """Один шаг сценария: текст и/или tool calls; delay — пауза между словами
    (имитация долгой генерации для тестов обрыва SSE-читателя)."""

    def __init__(
        self,
        text: str = "",
        tool_calls: list[ToolCall] | None = None,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.text = text
        self.tool_calls = tool_calls or []
        self.error = error
        self.delay = delay


class FakeLLMProvider:
    """Провайдер, раздающий заготовленные ответы по очереди; все запросы записываются."""

    name = "fake"
    capabilities = ProviderCapabilities(tools=True, streaming=True, json_schema=False)

    def __init__(self, turns: list[FakeTurn] | None = None) -> None:
        self.turns = list(turns or [])
        self.requests: list[tuple[str, LLMRequest]] = []

    def queue(self, *turns: FakeTurn) -> None:
        self.turns.extend(turns)

    def _next(self, model: str, request: LLMRequest) -> FakeTurn:
        self.requests.append((model, request))
        if not self.turns:
            return FakeTurn(text="(fake: сценарий исчерпан)")
        return self.turns.pop(0)

    async def complete(self, model: str, request: LLMRequest) -> LLMResponse:
        turn = self._next(model, request)
        if turn.error:
            raise turn.error
        return LLMResponse(
            text=turn.text,
            tool_calls=tuple(turn.tool_calls),
            usage=Usage(input_tokens=10, output_tokens=10),
            finish_reason="tool_calls" if turn.tool_calls else "stop",
        )

    def stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        return self._stream(model, request)

    async def _stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        turn = self._next(model, request)
        if turn.error:
            raise turn.error
        for word in turn.text.split(" "):
            if word:
                if turn.delay:
                    await asyncio.sleep(turn.delay)
                yield LLMEvent(type="text", text=word + " ")
        for call in turn.tool_calls:
            yield LLMEvent(type="tool_call", tool_call=call)
        yield LLMEvent(type="usage", usage=Usage(input_tokens=10, output_tokens=10))
        yield LLMEvent(type="finish", finish_reason="tool_calls" if turn.tool_calls else "stop")

    # helpers для сценариев
    @staticmethod
    def call(name: str, **args: Any) -> ToolCall:
        """Заготовка tool call для сценария."""
        return ToolCall(id=f"call_{name}", name=name, arguments=args)
