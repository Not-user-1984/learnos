"""Порт Telegram-шлюза: отправка сообщений и файлов."""

from typing import Protocol


class TelegramGateway(Protocol):
    """Отправка в Telegram; реализация — Bot API с прокси."""

    @property
    def configured(self) -> bool:
        """Токен задан?"""
        ...

    async def send_message(self, text: str, chat_id: str | None = None) -> int:
        """HTML-сообщение (<= 4096 символов), возвращает message_id."""
        ...

    async def send_document(self, path: str, caption: str = "", chat_id: str | None = None) -> int:
        """Файл с подписью, возвращает message_id."""
        ...
