"""Домен обучения: стейт-машина сессии, лог-события, правила финиша."""

import pytest

from app.modules.learning.domain import (
    FINAL_EVENT,
    LOG_EVENTS,
    TRANSITIONS,
    activity_done,
    allowed_events,
    can_finish,
    next_cursor,
    transition,
)


def test_all_defined_transitions_move_state():
    """Каждая запись TRANSITIONS действительно переводит состояние."""
    for (state, event), expected in TRANSITIONS.items():
        assert transition(state, event) == expected


def test_log_events_keep_state():
    """Лог-события (ask/answer/note/practice_log) не меняют состояние."""
    for state in ("theory", "check", "practice", "debrief"):
        for event in LOG_EVENTS:
            assert transition(state, event) == state


def test_unknown_event_raises_value_error():
    with pytest.raises(ValueError, match="недопустимо"):
        transition("theory", "go_practice")  # go_practice разрешён только из check
    with pytest.raises(ValueError, match="недопустимо"):
        transition("debrief", "theory_done")


def test_allowed_events_contain_transitions_and_logs():
    events = allowed_events("theory")
    assert "theory_done" in events
    assert LOG_EVENTS.issubset(set(events))
    assert FINAL_EVENT not in events  # финиш разрешён только из debrief


def test_allowed_events_debrief_contains_finish():
    events = allowed_events("debrief")
    assert FINAL_EVENT in events
    assert LOG_EVENTS.issubset(set(events))
    # переходов из debrief нет — только лог и финиш
    assert set(events) == LOG_EVENTS | {FINAL_EVENT}


def test_can_finish_happy_path():
    can_finish("debrief", "active", answers=2)  # не бросает


def test_can_finish_requires_feynman_answers():
    """Фейнман-гейт (R-18): без единого answer сессию закрыть нельзя."""
    import pytest

    with pytest.raises(ValueError, match="фейнмана"):
        can_finish("debrief", "active", answers=0)
    can_finish("debrief", "active", answers=1)  # один проговор уже честен


def test_can_finish_rejects_wrong_state():
    with pytest.raises(ValueError, match="debrief"):
        can_finish("practice", "active")


def test_can_finish_rejects_closed_session():
    with pytest.raises(ValueError, match="finished"):
        can_finish("debrief", "finished")


def test_activity_done_and_next_cursor():
    assert activity_done(3, 2) is True  # курсор за последней главой
    assert activity_done(2, 2) is False
    assert activity_done(1, 0) is False  # нет глав — не пройдена
    assert next_cursor(5, 3) == 4  # не дальше total+1
    assert next_cursor(2, 3) == 2
