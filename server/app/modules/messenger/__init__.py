"""Модуль «Messenger»: Telegram-шлюз проекта — отправка текста, блоков, глав книги."""

from ...kernel.module import Module


class MessengerModule(Module):
    """Отправка в Telegram из любого агента; самодостаточно (Bot API + прокси)."""

    name = "messenger"

    def wire(self, c) -> None:
        from .bot_api import TelegramBotGateway
        from .service import MessengerService

        c.messenger = MessengerService(TelegramBotGateway(c.settings))

    def routers(self, c):
        from .api import make_router

        return [make_router(c.messenger)]

    def tools(self, c):
        from .tools import messenger_tools

        return messenger_tools(c)
