"""Минимальный cron-парсер (B-010): «m h dom mon dow», поля со *, списками, диапазонами, шагами."""

from __future__ import annotations

from datetime import datetime, timedelta


def _parse_field(field: str, low: int, high: int) -> set[int] | None:
    """Допустимые значения поля; None — любое («*»)."""
    if field == "*":
        return None
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
            if step != 1:  # «5/2» — от 5 до конца диапазона
                end = high
        values.update(range(start, end + 1, step))
    return values


def _matches(expr: str, now: datetime) -> bool:
    parts = expr.split()
    if len(parts) != 5:
        return False
    minute, hour, dom, mon, dow = (
        _parse_field(parts[0], 0, 59),
        _parse_field(parts[1], 0, 23),
        _parse_field(parts[2], 1, 31),
        _parse_field(parts[3], 1, 12),
        _parse_field(parts[4], 0, 6),
    )
    return (
        (minute is None or now.minute in minute)
        and (hour is None or now.hour in hour)
        and (dom is None or now.day in dom)
        and (mon is None or now.month in mon)
        and (dow is None or now.weekday() in dow)
    )


def cron_due(expr: str, last_run: str | None, now: datetime) -> bool:
    """Настал ли момент с прошлого запуска (last_run ISO) до now.

    Поминутный проход: сон хомлаба даёт длинные окна — catch-up срабатывает
    один раз (первое совпадение), last_run обновляется запуском.
    """
    if not last_run:
        return True
    try:
        last = datetime.fromisoformat(last_run)
    except ValueError:
        return True
    cursor = last.replace(second=0, microsecond=0) + timedelta(minutes=1)
    floor = now - timedelta(days=2)  # защита от вечного прошлого
    if cursor < floor:
        cursor = floor
    while cursor <= now:
        if _matches(expr, cursor):
            return True
        cursor += timedelta(minutes=1)
    return False
