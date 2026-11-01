"""Домен обучения: стейт-машина сессии (переходы как в v1), правила активности."""

from dataclasses import dataclass, field

TRANSITIONS = {
    ("theory", "theory_done"): "check",
    ("check", "next_block"): "theory",
    ("check", "go_practice"): "practice",
    ("practice", "practice_done"): "debrief",
}

LOG_EVENTS = {"ask", "answer", "note", "practice_log"}
FINAL_EVENT = "finish_session"


@dataclass(frozen=True, slots=True)
class SessionState:
    """Состояние сессии: где мы и что можно делать дальше."""

    status: str
    state: str
    allowed_events: tuple[str, ...] = ()
    transcript: list[dict] = field(default_factory=list)


def allowed_events(state: str) -> tuple[str, ...]:
    """Разрешённые события в состоянии: переходы + лог-события + финиш из debrief."""
    events = sorted({ev for (st, ev) in TRANSITIONS if st == state} | LOG_EVENTS)
    if state == "debrief":
        events = sorted(events + [FINAL_EVENT])
    return tuple(events)


def transition(state: str, event: str) -> str | None:
    """Новое состояние по событию; None — событие не переводит (лог или неверное).

    Raises:
        ValueError: событие недопустимо в этом состоянии.
    """
    new_state = TRANSITIONS.get((state, event))
    if new_state is not None:
        return new_state
    if event in LOG_EVENTS:
        return state
    raise ValueError(f"событие '{event}' недопустимо в состоянии '{state}'")


def can_finish(state: str, status: str, answers: int = 0) -> None:
    """Проверить, что сессию можно завершить.

    Фейнман-гейт (R-18 аудита): ядро продукта — «знание рождается через
    понимание», поэтому сессия не закрывается без единого проговора
    (answer-события); раньше это держалось только промптом агента.

    Raises:
        ValueError: не из debrief, уже закрыта или не было ни одного ответа.
    """
    if status != "active":
        raise ValueError(f"сессия уже {status}")
    if state != "debrief":
        raise ValueError(f"finish allowed only from state 'debrief' (сейчас '{state}')")
    if answers < 1:
        raise ValueError(
            "урок нельзя закрыть без единого ответа фейнмана — задай вопрос и выслушай ответ "
            "(или продолжи урок позже)"
        )


def transcript_entry(state: str, event: str, payload: dict, ts: str) -> dict:
    """Запись в транскрипт сессии."""
    return {"ts": ts, "state": state, "event": event, "payload": payload}


def activity_done(cursor_chapter: int, total_chapters: int) -> bool:
    """Активность пройдена, когда курсор за последней главой."""
    return total_chapters > 0 and cursor_chapter > total_chapters


def next_cursor(cursor_chapter: int, total_chapters: int) -> int:
    """Курсор не дальше числа глав + 1 (done)."""
    return min(cursor_chapter, total_chapters + 1)
