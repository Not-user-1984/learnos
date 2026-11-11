"""Таблица решений по предложениям (B-010): репо task_ai может быть read-only на проде."""

from sqlalchemy import Column, Integer, Table, Text

from ....kernel.db import metadata

proposal_decisions = Table(
    "proposal_decisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # task | branch | prompt
    Column("kind", Text, nullable=False),
    # task_id | branch | change_id
    Column("ref", Text, nullable=False),
    # accepted | rejected
    Column("decision", Text, nullable=False),
    Column("decided_at", Text, nullable=False),
)
