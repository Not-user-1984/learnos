"""Messenger: чанкинг для Telegram и конвертация MD → HTML."""

from __future__ import annotations

from app.modules.messenger.bot_api import chunk_for_telegram
from app.modules.messenger.service import md_to_telegram_html


def test_chunks_respect_paragraph_boundaries():
    text = "\n\n".join(f"Абзац {i}. " + "слово " * 120 for i in range(10))
    chunks = chunk_for_telegram(text, limit=3800)
    assert all(len(c) <= 3800 for c in chunks)
    assert "".join(chunks).replace("\n\n", "").count("Абзац") == 10
    assert len(chunks) >= 2


def test_single_short_text_one_chunk():
    assert chunk_for_telegram("Привет") == ["Привет"]


def test_overlong_paragraph_split_by_sentences():
    para = " ".join(f"Предложение номер {i} достаточно длинное." for i in range(200))
    chunks = chunk_for_telegram(para, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert len(chunks) > 5


def test_md_to_telegram_html():
    html = md_to_telegram_html("## Заголовок\n\n**жирный** и `код`\n\n> цитата")
    assert "<b>Заголовок</b>" in html
    assert "<b>жирный</b>" in html
    assert "<code>код</code>" in html
    assert "<i>цитата</i>" in html


def test_html_escaping():
    html = md_to_telegram_html("a < b & c > d")
    assert "&lt;" in html and "&amp;" in html and "&gt;" in html


def test_html_chunks_fit_telegram_limit_after_conversion():
    """Куски считаются ПОСЛЕ конвертации в HTML: экрелирование и теги не толкают за 4096 (R-22)."""
    from app.modules.messenger.service import _html_chunks

    text = "\n\n".join(f"Параграф {i}: a < b & c > d **жирный** `код` " + "слово " * 80 for i in range(20))
    chunks = _html_chunks(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 3800 for c in chunks)


def test_direct_route_survives_second_call(monkeypatch):
    """После успешной прямой отправки маршрут «""» не ломает следующий вызов (R-22)."""
    import asyncio

    import httpx

    import app.modules.messenger.bot_api as bot_api
    from app.modules.messenger.bot_api import TelegramBotGateway

    class _Settings:
        telegram_token = "t"
        telegram_chat_id = "1"
        telegram_proxy = None

    gw = TelegramBotGateway(_Settings())  # type: ignore[arg-type]
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})
    )
    real_client = httpx.AsyncClient

    def patched_client(**kw):
        kw["transport"] = transport
        return real_client(**kw)

    monkeypatch.setattr(bot_api.httpx, "AsyncClient", patched_client)

    async def call_twice() -> None:
        await gw.send_message("первое")
        await gw.send_message("второе")  # раньше падало: Proxy("") → ValueError

    asyncio.run(call_twice())
    assert gw._route == ""  # noqa: SLF001 — прямой маршрут запомнен
