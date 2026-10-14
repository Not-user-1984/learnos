"""Совместимая точка входа в SQLite для скиллов (raw sqlite3, как в v1)."""

import sqlite3

from .paths import DB_PATH


def get_db() -> sqlite3.Connection:
    """Соединение с БД ядра (только для drop-in скиллов)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Схема создаётся миграциями; здесь только проверка файла."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
