"""Генерация строковых uid с префиксами (blk_, src_, …)."""

import secrets
from typing import Protocol


class IdGenerator(Protocol):
    """Порт генератора идентификаторов: prefix + 8 hex."""

    def new(self, prefix: str) -> str:
        """Новый uid вида ``blk_1a2b3c4d``."""
        ...


class UuidHexGenerator:
    """Реализация на secrets: 8 hex-символов."""

    def new(self, prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(4)}"
