"""Таблица повторений."""

from sqlalchemy import Column, Integer, Table, Text

from ....kernel.db import metadata

review_items = Table(
    "review_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("block_uid", Text, nullable=False, unique=True),
    Column("ease", Integer, nullable=False, server_default="25"),  # ease×10, чтобы жить в INTEGER
    Column("interval_days", Integer, nullable=False, server_default="1"),
    Column("due_at", Text, nullable=False),
    Column("last_quality", Integer),
    Column("reps", Integer, nullable=False, server_default="0"),
    Column("updated_at", Text, nullable=False),
)
