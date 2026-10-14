"""Таблица настроек (key → json)."""

from sqlalchemy import Column, Text

from ....kernel.db import metadata


def _make_table():
    from sqlalchemy import Table

    return Table(
        "settings",
        metadata,
        Column("key", Text, primary_key=True),
        Column("value_json", Text, nullable=False),
    )


settings_table = _make_table()
