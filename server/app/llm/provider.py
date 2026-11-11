"""Протокол LLM-провайдера и нормализация ошибок."""

from typing import Protocol, runtime_checkable

from .types import LLMRequest, LLMResponse, ProviderCapabilities


@runtime_checkable
class LLMProvider(Protocol):
    """Адаптер к API конкретного провайдера моделей."""

    name: str
    capabilities: ProviderCapabilities

    async def complete(self, model: str, request: LLMRequest) -> LLMResponse:
        """Один ответ целиком."""
        ...

    def stream(self, model: str, request: LLMRequest):
        """Ответ потоком: текст по кускам, вызовы инструментов — целиком, когда собраны."""
        ...

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Эмбеддинги батча текстов (OpenAI-совместимый /embeddings, B-008)."""
        ...
