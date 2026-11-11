"""Доступ к SQLite через SQLAlchemy: engine, фабрика сессий, UnitOfWork с очередью событий."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .events import EventBus, PendingEvents

log = logging.getLogger("learnos.db")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

# sqlite-vec (B-008): расширение векторного поиска; отсутствие колеса не фатально —
# поиск деградирует в чистый FTS
try:
    import sqlite_vec
except ImportError:  # pragma: no cover — платформа без колеса
    sqlite_vec = None


def make_engine(url: str, *, echo: bool = False) -> Engine:
    """Engine для SQLite с WAL, foreign_keys и (если доступен) sqlite-vec."""
    engine = create_engine(url, echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        if sqlite_vec is not None:
            try:
                dbapi_conn.enable_load_extension(True)
                sqlite_vec.load(dbapi_conn)
                dbapi_conn.enable_load_extension(False)
            except Exception:  # noqa: BLE001 — векторный поиск опционален
                log.warning("sqlite-vec не загрузился — поиск на чистом FTS", exc_info=True)
        cur.close()

    return engine


class UnitOfWork:
    """Одна транзакция = один use-case. События публикуются только после успешного коммита."""

    def __init__(self, session: Session, bus: EventBus, publisher: str) -> None:
        self.session = session
        self.bus = bus
        self.pending = PendingEvents()
        self._publisher = publisher

    def emit(self, event: object) -> None:
        """Запомнить доменное событие до конца транзакции."""
        self.pending.add(event, self._publisher)  # type: ignore[arg-type]

    def commit(self) -> None:
        self.session.commit()
        for envelope in self.pending.drain():
            self.bus.publish(envelope)

    def rollback(self) -> None:
        self.session.rollback()
        self.pending.drain()


class UnitOfWorkFactory:
    """Фабрика UoW над одной фабрикой сессий."""

    def __init__(self, factory: sessionmaker[Session], bus: EventBus, publisher: str = "app") -> None:
        self._factory = factory
        self._bus = bus
        self._publisher = publisher

    @contextmanager
    def __call__(self) -> Iterator[UnitOfWork]:
        """Контекст use-case: commit+publish при нормальном выходе, rollback при исключении."""
        session = self._factory()
        uow = UnitOfWork(session, self._bus, self._publisher)
        try:
            yield uow
            uow.commit()
        except Exception:
            uow.rollback()
            raise
        finally:
            session.close()
