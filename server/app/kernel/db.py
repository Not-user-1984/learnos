"""Доступ к SQLite через SQLAlchemy: engine, фабрика сессий, UnitOfWork с очередью событий."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .events import EventBus, PendingEvents

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str, *, echo: bool = False) -> Engine:
    """Engine для SQLite с WAL и foreign_keys."""
    engine = create_engine(url, echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
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
