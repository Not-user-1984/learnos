"""Таблицы модуля knowledge."""

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
)

from ....kernel.db import metadata

categories = Table(
    "categories",
    metadata,
    Column("path", Text, primary_key=True),
    Column("title", Text, nullable=False),
    Column("parent_path", Text),
    Column("color", Text),
    Column("icon", Text),
    Column("sort", Integer, nullable=False, server_default="0"),
)

blocks = Table(
    "blocks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("block_uid", Text, nullable=False, unique=True),
    Column("kind", Text, nullable=False, server_default="lesson"),
    Column("title", Text, nullable=False),
    Column("summary", Text),
    Column("category_path", Text),
    Column("category_status", Text, nullable=False, server_default="suggested"),
    Column("path", Text, nullable=False),
    Column("session_uid", Text),
    Column("conversation_uid", Text),
    Column("activity_uid", Text),
    Column("weak_spots_count", Integer, nullable=False, server_default="0"),
    Column("verified", Boolean, nullable=False, server_default="0"),  # блок из сессии (R-18)
    Column("version", Integer, nullable=False, server_default="1"),
    Column("review_json", Text, nullable=False, server_default="{}"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
Index("ix_blocks_category_path", blocks.c.category_path)
Index("ix_blocks_updated_at", blocks.c.updated_at)

block_tags = Table(
    "block_tags",
    metadata,
    Column("block_uid", Text, nullable=False, primary_key=True),
    Column("tag", Text, nullable=False, primary_key=True),
)
Index("ix_block_tags_tag", block_tags.c.tag)

block_sources = Table(
    "block_sources",
    metadata,
    Column("block_uid", Text, nullable=False),
    Column("source_uid", Text, nullable=False),
    Column("chapter_idx", Integer),
)
Index("ix_block_sources_source_uid", block_sources.c.source_uid)

block_links = Table(
    "block_links",
    metadata,
    Column("from_uid", Text, nullable=False, primary_key=True),
    Column("to_uid", Text, nullable=False, primary_key=True),
)

block_versions = Table(
    "block_versions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("block_uid", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("reason", Text),
    Column("conversation_uid", Text),
    Column("created_at", Text, nullable=False),
)
concepts = Table(
    "concepts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("uid", Text, nullable=False, unique=True),
    Column("block_uid", Text, ForeignKey("blocks.block_uid"), nullable=False),
    Column("term", Text, nullable=False),
    Column("definition", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)
Index("ix_concepts_block", concepts.c.block_uid)
