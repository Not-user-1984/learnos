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
