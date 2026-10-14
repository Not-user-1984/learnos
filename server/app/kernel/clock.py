"""Часы как порт: домен не знает, какое «сейчас»."""

import datetime
from typing import Protocol


class Clock(Protocol):
    """Порт источника времени."""

    def now(self) -> datetime.datetime:
        """Текущий момент с таймзоной."""
        ...


class SystemClock:
    """Системные часы."""

    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


def now_iso(clock: Clock) -> str:
    """ISO-строка с таймзоной для записи в БД и frontmatter."""
    return clock.now().isoformat(timespec="seconds")
