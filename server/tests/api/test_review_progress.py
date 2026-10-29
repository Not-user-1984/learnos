"""Прогресс быстрого разбора: review_progress в API разговора и SSE (T-046 Э1)."""

from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from tests.api.test_book_structure import ENTRIES, _add_book_source
from tests.api.test_sse import parse_sse


def _review_conversation(container) -> dict:
    """Разговор quick-разбора по книге из 3 глав (после куратора структуры)."""
    src = _add_book_source(container)
    container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    act = container.learning.start_activity(src["uid"])
    return container.chat.create_conversation(mode="quick", activity=act["uid"], chapter=1)


def test_conversation_returns_review_progress(client, container):
    """Прогресс из БД: главы пройдено/всего, текущая глава с читаемым названием."""
    conv = _review_conversation(container)
    p = client.get(f"/api/conversations/{conv['uid']}").json()["review_progress"]
    assert p["done_chapters"] == 0 and p["total_chapters"] == 3
    assert p["current_chapter"] == 1
    assert "Введение" in p["current_title"]
    assert p["status"] == "active" and p["kind"] == "book"


def test_review_progress_follows_mark_chapter_done(client, container):
    """mark_chapter_done двигает прогресс; последняя глава — книга разобрана."""
    conv = _review_conversation(container)

    container.learning.mark_chapter_done(conversation_uid=conv["uid"])
    p = client.get(f"/api/conversations/{conv['uid']}").json()["review_progress"]
    assert p["done_chapters"] == 1 and p["current_chapter"] == 2

    container.learning.mark_chapter_done(conversation_uid=conv["uid"], chapter=3)
    p = client.get(f"/api/conversations/{conv['uid']}").json()["review_progress"]
    assert p["done_chapters"] == 3 and p["status"] == "done"
    assert p["current_chapter"] is None and p["current_title"] is None


def test_conversation_without_activity_has_no_review_progress(client):
    """Разговор без активности — прогресс разбора отсутствует, ничего не ломается."""
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    body = client.get(f"/api/conversations/{conv['uid']}").json()
    assert body["review_progress"] is None


def test_review_progress_sse_event_after_mark_chapter_done(client, container, fake_llm):
    """Агент отметил главу — событие review_progress уходит в стрим без перечитывания разговора."""
    conv = _review_conversation(container)
    fake_llm.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("mark_chapter_done")]),
        FakeTurn(text="Глава разобрана. Идём дальше?"),
    )
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "дальше"}
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    progress = [data for name, data in events if name == "review_progress"]
    assert progress and progress[-1]["done_chapters"] == 1
    assert progress[-1]["current_chapter"] == 2
