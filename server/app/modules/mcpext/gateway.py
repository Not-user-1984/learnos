"""Асинхронный клиент внешних MCP-серверов (mcp SDK, streamable HTTP).

Каждая операция открывает своё соединение: нет общего состояния, ошибки одного
сервера не влияют на остальные и не роняют приложение.
"""

import logging
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

log = logging.getLogger("learnos.mcpext")


def describe_error(e: BaseException) -> str:
    """Человекочитаемая ошибка: разворачивает ExceptionGroup (TaskGroup mcp-клиента)."""
    if isinstance(e, BaseExceptionGroup):
        return "; ".join(describe_error(sub) for sub in e.exceptions) or str(e)
    return f"{type(e).__name__}: {e}"


def _http_client(headers: dict[str, str] | None, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=headers or {}, timeout=httpx.Timeout(timeout_s))


async def list_remote_tools(
    url: str, headers: dict[str, str] | None = None, timeout_s: float = 20.0
) -> list[dict[str, Any]]:
    """Подключиться и получить каталог инструментов; бросает исключение при недоступности."""
    async with _http_client(headers, timeout_s) as client:
        async with streamable_http_client(url.strip(), http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                res = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": (t.description or "").strip(),
                        "input_schema": (t.input_schema or {"type": "object", "properties": {}}),
                    }
                    for t in res.tools
                ]


async def call_remote_tool(
    url: str,
    tool: str,
    arguments: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Вызвать инструмент внешнего сервера; ошибки сервера → {"error", "message"}."""
    async with _http_client(headers, timeout_s) as client:
        async with streamable_http_client(url.strip(), http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                res = await session.call_tool(tool, arguments or {})
    if res.isError:
        return {"error": "remote_tool_error", "message": _result_text(res)[:500]}
    return {"ok": True, "result": _result_text(res)}


def _result_text(res) -> str:
    parts = [
        getattr(block, "text", "") for block in (res.content or []) if getattr(block, "type", "") == "text"
    ]
    return "\n".join(p for p in parts if p) or "(пустой ответ MCP)"
