"""Инструменты messenger: отправка в Telegram из любого агента."""

from pydantic import BaseModel

from ...kernel.errors import ValidationFailed
from ...kernel.tools.spec import ToolContext, ToolSpec


class SendTextArgs(BaseModel):
    """send_telegram_text: текст читаемыми сообщениями."""

    text: str


class SendBlockArgs(BaseModel):
    """send_block_to_telegram: блок базы знаний (выноска + .md файлом)."""

    block_uid: str


class SendChapterArgs(BaseModel):
    """send_chapter_to_telegram: глава книги почитать в Telegram."""

    source: str | int
    chapter: int


def messenger_tools(c) -> list[ToolSpec]:
    """Инструменты отправки в Telegram."""
    svc = c.messenger

    def _require():
        if not svc.configured:
            raise ValidationFailed("Telegram не настроен: задай LEARNOS_TELEGRAM_TOKEN")

    def send_telegram_text(args: SendTextArgs, ctx: ToolContext) -> dict:
        del ctx
        _require()
        return svc.send_text(args.text)

    def send_block_to_telegram(args: SendBlockArgs, ctx: ToolContext) -> dict:
        del ctx
        _require()
        return svc.send_block(c.knowledge, args.block_uid)

    def send_chapter_to_telegram(args: SendChapterArgs, ctx: ToolContext) -> dict:
        del ctx
        _require()
        return svc.send_chapter(c.library, c.knowledge, args.source, args.chapter)

    return [
        ToolSpec(
            name="send_telegram_text",
            module="messenger",
            description="Отправить текст пользователю в Telegram (читаемыми сообщениями).",
            args_model=SendTextArgs,
            handler=send_telegram_text,
            label="Отправляю в Telegram",
        ),
        ToolSpec(
            name="send_block_to_telegram",
            module="messenger",
            description="Отправить блок базы знаний в Telegram: выноска + полный MD-файл.",
            args_model=SendBlockArgs,
            handler=send_block_to_telegram,
            label="Блок в Telegram",
        ),
        ToolSpec(
            name="send_chapter_to_telegram",
            module="messenger",
            description="Отправить главу книги в Telegram: почитать кусками + полный текст файлом.",
            args_model=SendChapterArgs,
            handler=send_chapter_to_telegram,
            label="Глава в Telegram",
        ),
    ]
