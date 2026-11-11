"""SQL-репозитории library: источники, главы, jobs."""

from __future__ import annotations

import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import NotFound
from .tables import chapters, jobs, sources


class SourceRepository:
    """Источники."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(sources.insert().values(**values)).inserted_primary_key[0])

    def get(self, session: Session, ref: str | int) -> dict:
        """Источник по uid или int id → dict (kind, title, status, meta…)."""
        row = self._row(session, ref)
        return _source_dict(row)

    def _row(self, session: Session, ref):
        cond = (
            sources.c.uid == ref if isinstance(ref, str) and not ref.isdigit() else sources.c.id == int(ref)
        )
        row = session.execute(select(sources).where(cond)).first()
        if row is None:
            raise NotFound(f"источник '{ref}' не найден")
        return row

    def find(self, session: Session, ref: str | int) -> dict | None:
        try:
            return self.get(session, ref)
        except NotFound:
            return None

    def list(self, session: Session, *, kind: str | None = None, q: str | None = None) -> list[dict]:
        stmt = select(sources)
        if kind:
            stmt = stmt.where(sources.c.kind == kind)
        if q:
            needle = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(sources.c.title).like(needle))
        rows = session.execute(stmt.order_by(sources.c.id.desc())).all()
        return [_source_dict(r) for r in rows]

    def update(self, session: Session, source_id: int, **values) -> None:
        values = {**values, "updated_at": values.get("updated_at")}
        session.execute(update(sources).where(sources.c.id == source_id).values(**values))

    def delete(self, session: Session, source_id: int) -> None:
        session.execute(delete(chapters).where(chapters.c.source_id == source_id))
        session.execute(delete(sources).where(sources.c.id == source_id))


class ChapterRepository:
    """Главы источника (файл на диске + строка в БД)."""

    def insert(self, session: Session, **values) -> int:
        return int(session.execute(chapters.insert().values(**values)).inserted_primary_key[0])

    def list(self, session: Session, source_id: int) -> list[dict]:
        rows = session.execute(
            select(chapters).where(chapters.c.source_id == source_id).order_by(chapters.c.idx)
        ).all()
        return [_chapter_dict(r) for r in rows]

    def get(self, session: Session, source_id: int, idx: int) -> dict:
        row = session.execute(
            select(chapters).where(chapters.c.source_id == source_id, chapters.c.idx == idx)
        ).first()
        if row is None:
            raise NotFound(f"глава {idx} источника {source_id} не найдена")
        return _chapter_dict(row)

    def update(self, session: Session, chapter_id: int, **values) -> None:
        session.execute(update(chapters).where(chapters.c.id == chapter_id).values(**values))

    def get_by_idx(self, session: Session, source_id: int, idx: int) -> dict | None:
        row = session.execute(
            select(chapters).where(chapters.c.source_id == source_id, chapters.c.idx == idx)
        ).first()
        return _chapter_dict(row) if row else None

    def delete(self, session: Session, chapter_id: int) -> None:
        session.execute(delete(chapters).where(chapters.c.id == chapter_id))

    def delete_for_source(self, session: Session, source_id: int) -> None:
        session.execute(delete(chapters).where(chapters.c.source_id == source_id))

    def count(self, session: Session, source_id: int) -> int:
        return int(
            session.execute(select(func.count()).where(chapters.c.source_id == source_id)).scalar_one()
        )


class JobRepository:
    """Фоновые jobs обработки."""

    def enqueue(self, session: Session, *, kind: str, target: str | None, total: int, now: str) -> int:
        return int(
            session.execute(
                jobs.insert().values(
                    kind=kind, target=target, status="queued", total=total, created_at=now, updated_at=now
                )
            ).inserted_primary_key[0]
        )

    def next_queued(self, session: Session) -> dict | None:
        row = session.execute(select(jobs).where(jobs.c.status == "queued").order_by(jobs.c.id)).first()
        return _job_dict(row) if row else None

    def get(self, session: Session, job_id: int) -> dict:
        row = session.execute(select(jobs).where(jobs.c.id == job_id)).first()
        if row is None:
            raise NotFound(f"job {job_id} не найден")
        return _job_dict(row)

    def update(self, session: Session, job_id: int, **values) -> None:
        session.execute(update(jobs).where(jobs.c.id == job_id).values(**values))

    def last_error(self, session: Session, *, target: str, kind: str = "process_source") -> str | None:
        """Ошибка последнего failed job обработки источника (показ в UI, B-001)."""
        row = session.execute(
            select(jobs.c.error)
            .where(jobs.c.target == target, jobs.c.kind == kind, jobs.c.status == "failed")
            .order_by(jobs.c.id.desc())
            .limit(1)
        ).first()
        return row[0] if row else None


def _source_dict(r) -> dict:
    return {
        "id": r.id,
        "uid": r.uid,
        "kind": r.kind,
        "title": r.title,
        "author": r.author,
        "url": r.url,
        "local_path": r.local_path,
        "status": r.status,
        "summary": r.summary,
        "meta": json.loads(r.meta_json or "{}"),
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _chapter_dict(r) -> dict:
    return {
        "id": r.id,
        "source_id": r.source_id,
        "idx": r.idx,
        "title": r.title,
        "path": r.path,
        "tokens_est": r.tokens_est,
        "summary": r.summary,
        "key_points": json.loads(r.key_points_json or "[]"),
        "has_exercises": bool(r.has_exercises),
        "number": r.number,
        "start_page": r.start_page,
        "end_page": r.end_page,
        "sections": json.loads(r.sections_json or "[]"),
    }


def _job_dict(r) -> dict:
    return {
        "id": r.id,
        "kind": r.kind,
        "target": r.target,
        "status": r.status,
        "progress": r.progress,
        "total": r.total,
        "message": r.message,
        "error": r.error,
    }
