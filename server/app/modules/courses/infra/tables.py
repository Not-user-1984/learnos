"""Таблицы курсов."""

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Table,
    Text,
)

from ....kernel.db import metadata

courses = Table(
    "courses",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("title", Text, nullable=False),
    Column("topic", Text, nullable=False),
    Column("description", Text),
    Column("category_path", Text),
    Column("status", Text, nullable=False, server_default="planned"),
    Column("plan_json", Text, nullable=False, server_default="{}"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

course_items = Table(
    "course_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("course_id", Integer, ForeignKey("courses.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("item_type", Text, nullable=False),
    Column("source_id", Integer, ForeignKey("sources.id")),
    Column("chapter_idx", Integer),
    Column("block_uid", Text),
    Column("note", Text),
    # доска курса (B-004): todo → doing → read|done; read = «прочитал сам»
    Column("status", Text, nullable=False, server_default="todo"),
)
