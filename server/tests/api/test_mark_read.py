"""«Прочитал сам»: глава отмечается из веб-читалки без разговора с агентом (BB-001)."""

from tests.api.test_book_structure import ENTRIES, _add_book_source

TOTAL = 3  # ENTRIES без front_matter (Титул, Оглавление): куратор оставляет 3 главы


def _book(container) -> dict:
    """Источник-книга из 3 глав после куратора структуры."""
    src = _add_book_source(container)
    container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    return src


def test_mark_read_creates_activity_if_none(client, container):
    """Без действующей активности — создаётся и курсор идёт вперёд."""
    src = _book(container)
    assert client.get("/api/activities?status=active").json() == []

    out = client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 2}).json()

    assert out["ok"] and out["marked_chapter"] == 2
    assert out["cursor_chapter"] == 3 and out["total_chapters"] == TOTAL
    assert out["status"] == "active"
    acts = client.get("/api/activities?status=active").json()
    assert len(acts) == 1 and acts[0]["source_uid"] == src["uid"]


def test_mark_read_idempotent_and_not_backwards(client, container):
    """Повтор идемпотентен; глава позади курсора его не откатывает."""
    src = _book(container)
    path = "/api/activities/mark-read"

    first = client.post(path, json={"source": src["uid"], "chapter": 2}).json()
    repeat = client.post(path, json={"source": src["uid"], "chapter": 2}).json()
    assert repeat["cursor_chapter"] == first["cursor_chapter"] == 3

    behind = client.post(path, json={"source": src["uid"], "chapter": 1}).json()
    assert behind["cursor_chapter"] == 3
    assert len(client.get("/api/activities?status=active").json()) == 1


def test_mark_read_last_chapter_finishes(client, container):
    """Последняя глава → изучение завершено."""
    src = _book(container)
    out = client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": TOTAL}).json()
    assert out["cursor_chapter"] == TOTAL + 1 and out["status"] == "done"


def test_mark_read_validates_chapter_and_source(client, container):
    """Номер главы вне книги и чужой источник — 409/404, без побочных эффектов."""
    src = _book(container)
    for chapter in (0, TOTAL + 1):
        resp = client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": chapter})
        assert resp.status_code == 409, chapter
    assert (
        client.post("/api/activities/mark-read", json={"source": "no-such", "chapter": 1}).status_code == 404
    )
    assert client.get("/api/activities?status=active").json() == []


def test_mark_read_feeds_review_progress(client, container):
    """Курсор из «прочитал сам» виден прогрессу разбора в чате — источник один."""
    src = _book(container)
    act = container.learning.start_activity(src["uid"])
    conv = container.chat.create_conversation(mode="quick", activity=act["uid"], chapter=1)

    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 2})
    p = client.get(f"/api/conversations/{conv['uid']}").json()["review_progress"]

    assert p["done_chapters"] == 2 and p["current_chapter"] == 3
    assert p["status"] == "active"
