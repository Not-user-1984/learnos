"""Мост sync→async: запустить корутину из синхронного кода (внутри или вне event loop)."""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any


def run_coro_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Выполнить корутину до конца из синхронного кода.

    Вне event loop — просто asyncio.run; внутри петли — отдельный поток со своей петлёй
    (блокирует вызывающий поток, но не ломает чужие задачи).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def _run() -> None:
        box["result"] = asyncio.run(coro)

    thread = threading.Thread(target=_run, name="learnos-coro-bridge")
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")
