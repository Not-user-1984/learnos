"""R-11: start_activity идемпотентен — повторные клики не плодят активности."""

from app.kernel.errors import NotFound


def _source(container) -> dict:
    return container.library.add_source("video", "Книга для чтения", url="https://youtu.be/idem123")


def test_start_activity_returns_same_active_activity(container):
    """Второй вызов без курса возвращает действующую активность с её курсором."""
    learning = container.learning
    src = _source(container)

    first = learning.start_activity(src["uid"])
    learning.mark_chapter_done(activity_ref=first["uid"], chapter=3)

    second = learning.start_activity(src["uid"])
    assert second["uid"] == first["uid"]
    assert second["id"] == first["id"]
    assert second["cursor_chapter"] == 4  # прогресс не сброшен в 1
    assert "уже идёт" in second["note"]

    # активностей по-прежнему одна
    active = [a for a in learning.list_activities() if a["source_id"] == src["id"]]
    assert len(active) == 1


def test_start_activity_separate_course_scopes(container, client):
    """Ключ — (источник, курс): активность курса и свободная — разные курсоры."""
    learning = container.learning
    src = _source(container)
    course = client.post("/api/courses", json={"topic": "тема"}).json()

    free = learning.start_activity(src["uid"])
    with_course = learning.start_activity(src["uid"], course_id=course["id"])
    assert free["uid"] != with_course["uid"]

    # повтор в том же ключе — та же активность
    again = learning.start_activity(src["uid"], course_id=course["id"])
    assert again["uid"] == with_course["uid"]


def test_mark_chapter_done_moves_only_bound_activity(container):
    """Курсор двигается у активности разговора — дубли его не размазывают (R-11)."""
    learning = container.learning
    src = _source(container)
    act = learning.start_activity(src["uid"])

    learning.mark_chapter_done(activity_ref=act["uid"], chapter=5)
    # «случайный» повторный старт — та же активность, курсор не откатился
    restarted = learning.start_activity(src["uid"])
    assert restarted["cursor_chapter"] == 6
    assert learning.get_activity(act["uid"])["cursor_chapter"] == 6


def test_start_activity_unknown_source(container):
    import pytest

    with pytest.raises(NotFound):
        container.learning.start_activity("src_missing00")
