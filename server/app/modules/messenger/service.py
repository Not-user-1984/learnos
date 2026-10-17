"""Сервис messenger: отправка текста, блоков БЗ и глав книги в Telegram."""

import re

from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.errors import NotFound
from .bot_api import chunk_for_telegram


def md_to_telegram_html(md: str) -> str:
    """Минимальный Markdown → HTML Telegram: заголовки жирным, **жирный**, `код`, кавычки."""
    text = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"^&gt;\s?(.+)$", r"<i>\1</i>", text, flags=re.M)
    return text


class MessengerService:
    """Use-cases отправки; гейтвей внедряется (Bot API в проде, мок в тестах)."""

    def __init__(self, gateway) -> None:
        self._gw = gateway

    @property
    def configured(self) -> bool:
        """Токен задан."""
        return self._gw.configured

    def send_text(self, text: str) -> dict:
        """Текст одним-несколькими сообщениями (читаемыми кусками)."""
        ids = []
        for chunk in chunk_for_telegram(text):
            ids.append(run_coro_sync(self._gw.send_message(md_to_telegram_html(chunk))))
        return {"ok": True, "message_ids": ids, "chunks": len(ids)}

    def send_block(self, knowledge, block_uid: str) -> dict:
        """Блок БЗ: сообщение-выноска + полный .md файлом."""
        block = knowledge.get_block(block_uid)
        head = f"📚 <b>{_esc(block.meta.title)}</b>\n<i>{_esc(block.meta.summary or '')}</i>"
        message_id = run_coro_sync(self._gw.send_message(head))
        doc_id = run_coro_sync(
            self._gw.send_document(
                _kb_file(knowledge, block.meta.path),
                caption=f"📖 {_esc(block.meta.title)} — полный блок (MD)",
            )
        )
        return {"ok": True, "message_ids": [message_id, doc_id]}

    def send_chapter(self, library, knowledge, source_ref: str | int, chapter: int) -> dict:
        """Глава книги: выноска (title + summary) и полный текст читаемыми кусками + .md файлом."""
        src = library.get_source(source_ref)
        chapters = [ch for ch in src.get("chapters", []) if ch["idx"] == chapter]
        if not chapters:
            raise NotFound(f"глава {chapter} источника не найдена")
        ch = chapters[0]
        head = (
            f"📖 <b>{_esc(src['title'])}</b> — глава {ch['idx']}. {_esc(ch['title'])}\n"
            f"<i>{_esc(ch.get('summary') or '')}</i>"
        )
        ids = [run_coro_sync(self._gw.send_message(head))]
        text = library.read_chapter(source_ref, chapter, 0, 10_000_000)["text"]
        for chunk in chunk_for_telegram(text)[
            1:6
        ]:  # первая порция дублирует выноску меньше; читаем до 6 кусков
            ids.append(run_coro_sync(self._gw.send_message(md_to_telegram_html(chunk))))
        doc_id = run_coro_sync(
            self._gw.send_document(
                _chapter_file(library, source_ref, chapter),
                caption=f"Глава {ch['idx']}. {_esc(ch['title'])} (полный текст)",
            )
        )
        ids.append(doc_id)
        return {"ok": True, "message_ids": ids}


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kb_file(knowledge, file_stem: str) -> str:
    import pathlib

    return str(pathlib.Path(knowledge._files.blocks_dir / f"{file_stem}.md"))  # noqa: SLF001 — экспорт файла как есть


def _chapter_file(library, source_ref, chapter: int) -> str:
    with library._uow() as uow:  # noqa: SLF001
        src = library._sources.get(uow.session, source_ref)
        ch = library._chapters.get(uow.session, src["id"], chapter)
    return ch["path"]
