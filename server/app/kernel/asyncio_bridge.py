"""Мост sync→async: выполнить корутину из синхронного кода.

Все фоновые вызовы (structured-агенты, summarize, Telegram) идут через одну
выделенную фоновую петлю (R-23 аудита): раньше каждый run_coro_sync делал
asyncio.run с новой петлёй — провайдер пересоздавал AsyncOpenAI-клиенты,
старые не закрывались (утечка сокетов на длинных книгах).
"""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

_BG_LOOP: asyncio.AbstractEventLoop | None = None
_BG_LOCK = threading.Lock()


def _background_loop() -> asyncio.AbstractEventLoop:
    """Единственная фоновая петля процесса (демон-поток)."""
    global _BG_LOOP
    if _BG_LOOP is None:
        with _BG_LOCK:
            if _BG_LOOP is None:
                started = threading.Event()

                def _runner() -> None:
                    global _BG_LOOP
                    _BG_LOOP = asyncio.new_event_loop()
                    asyncio.set_event_loop(_BG_LOOP)
                    started.set()
                    _BG_LOOP.run_forever()

                threading.Thread(target=_runner, name="learnos-bg-loop", daemon=True).start()
                started.wait(timeout=5)
    assert _BG_LOOP is not None
    return _BG_LOOP


def run_coro_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Выполнить корутину до конца из синхронного кода.

    Вне петли — фоновой петлёй (клиенты и кэши живут долго); из чужой петли —
    отдельный поток со временной петлёй (блокирует вызывающий поток, редкий путь).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run_coroutine_threadsafe(coro, _background_loop()).result()

    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001 — исключение потока должно дойти до вызывающего
            box["error"] = e

    thread = threading.Thread(target=_run, name="learnos-coro-bridge")
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")
