"""Мост sync→async: исключение корутины обязано дойти до вызывающего, а не потеряться в потоке."""

import asyncio

import pytest

from app.kernel.asyncio_bridge import run_coro_sync


async def _ok() -> int:
    await asyncio.sleep(0)
    return 42


async def _boom() -> None:
    await asyncio.sleep(0)
    raise ValueError("корутина упала")


def test_result_outside_loop() -> None:
    assert run_coro_sync(_ok()) == 42


def test_raise_outside_loop() -> None:
    with pytest.raises(ValueError, match="корутина упала"):
        run_coro_sync(_boom())


async def test_raise_inside_loop_via_thread() -> None:
    # внутри петли мост уходит в отдельный поток — исключение должно вернуться
    with pytest.raises(ValueError, match="корутина упала"):
        run_coro_sync(_boom())


async def test_result_inside_loop_via_thread() -> None:
    assert run_coro_sync(_ok()) == 42
