"""Домен повторений: SM-2 (чистые функции)."""


def sm2_review(quality: int, ease: float, interval_days: int, reps: int) -> tuple[float, int, int]:
    """Один шаг SM-2: качество 0–5 → (новый ease, интервал, счётчик повторений).

    quality < 3 — провал: интервал сбрасывается на 1, ease падает.
    """
    if not 0 <= quality <= 5:
        raise ValueError("quality должен быть 0–5")
    if quality < 3:
        # провал: интервал сброс, ease падает; due уводится на сутки вперёд —
        # лапс «остывает» и не выскакивает в очередь немедленно (R-17)
        return (max(1.3, ease - 0.2), 1, 0)
    new_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, round(new_ease, 3))
    if reps == 0:
        return (new_ease, 1, reps + 1)
    if reps == 1:
        return (new_ease, 6, reps + 1)
    return (new_ease, max(1, round(interval_days * ease)), reps + 1)


def queue_priority(item: dict) -> tuple[int, str]:
    """Приоритет очереди: сначала слабые места, затем созревшие по due_at."""
    weak = 1 if item.get("weak_spots_count", 0) > 0 else 0
    return (-weak, str(item.get("due_at") or ""))
