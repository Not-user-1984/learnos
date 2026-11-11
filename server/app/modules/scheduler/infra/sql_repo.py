"""SQL-репозиторий расписаний (B-010)."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .tables import schedules


class ScheduleRepository:
    """Расписания: дефолты, включение, атомарный захват запуска."""

    def ensure(self, session: Session, name: str, cron: str, action: str) -> None:
        if session.execute(select(schedules).where(schedules.c.name == name)).first() is None:
            session.execute(schedules.insert().values(name=name, cron=cron, action=action, enabled=0))

    def all(self, session: Session) -> list[dict]:
        rows = session.execute(select(schedules).order_by(schedules.c.id)).all()
        return [dict(r._mapping) for r in rows]

    def get(self, session: Session, name: str) -> dict | None:
        row = session.execute(select(schedules).where(schedules.c.name == name)).first()
        return dict(row._mapping) if row else None

    def set_enabled(self, session: Session, name: str, enabled: bool) -> None:
        session.execute(update(schedules).where(schedules.c.name == name).values(enabled=1 if enabled else 0))

    def try_acquire(self, session: Session, schedule_id: int, now_iso: str) -> bool:
        """Атомарный лок: один запуск одновременно на задачу."""
        result = session.execute(
            update(schedules)
            .where(schedules.c.id == schedule_id, schedules.c.last_status != "running")
            .values(last_status="running", last_run_at=now_iso)
        )
        return result.rowcount > 0

    def finish(self, session: Session, schedule_id: int, status: str, now_iso: str) -> None:
        session.execute(
            update(schedules)
            .where(schedules.c.id == schedule_id)
            .values(last_status=status, last_run_at=now_iso)
        )
