"""B-005: дашборд «Сегодня» и старт сессии по элементу курса из UI."""

from app.modules.learning.infra.tables import activities as activities_table
from app.modules.library.infra.tables import chapters as chapters_table


def _mk_source_with_chapters(container, n: int = 3, kind: str = "book") -> dict:
    src = container.library.add_source(kind, "Книга дня", url=None)
    with container.uow() as uow:
        for idx in range(1, n + 1):
            uow.session.execute(
                chapters_table.insert().values(
                    source_id=src["id"],
                    idx=idx,
                    title=f"Глава {idx}",
                    path=f"/tmp/today-ch{idx}.md",
                    tokens_est=100,
                )
            )
    return src


def test_today_empty(client):
    """Пустая база — честный пустой снимок без ошибок."""
    out = client.get("/api/today").json()
    assert out["active_session"] is None
    assert out["next_course_items"] == []
    assert out["reading"] == []
    assert out["inbox_count"] == 0
    assert out["sources_attention"] == []
    assert out["review"] == {"due_today": 0}


def test_today_with_data_and_item_start(client, container, fake_llm):
    """Активный курс даёт next_item; /start создаёт разговор и сессию с course_item_id."""
    src = _mk_source_with_chapters(container)
    client.post(
        "/api/courses",
        json={
            "topic": "сегодня",
            "items": [{"item_type": "chapter", "source": src["uid"], "chapter": 1}],
        },
    ).json()

    # чтение книги — активность создаётся mark-read
    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})

    out = client.get("/api/today").json()
    assert out["reading"] and out["reading"][0]["source_uid"] == src["uid"]
    # курс стал done (единственный элемент read) → next_course_items пуст
    assert out["next_course_items"] == []

    # второй курс с незакрытым элементом → появляется в «дальше»
    course2 = client.post(
        "/api/courses",
        json={
            "topic": "второй",
            "items": [
                {"item_type": "chapter", "source": src["uid"], "chapter": 2},
                {"item_type": "chapter", "source": src["uid"], "chapter": 3},
            ],
        },
    ).json()
    out = client.get("/api/today").json()
    assert out["next_course_items"][0]["course_uid"] == course2["uid"]
    assert out["next_course_items"][0]["item_type"] == "chapter"

    # старт по элементу: разговор session-режима + активная сессия
    started = client.post(f"/api/courses/{course2['uid']}/items/{course2['items'][0]['id']}/start").json()
    assert started["conversation_uid"].startswith("cnv_")
    assert started["session_uid"].startswith("ses_")

    out = client.get("/api/today").json()
    assert out["active_session"]["conversation_uid"] == started["conversation_uid"]

    conv = client.get(f"/api/conversations/{started['conversation_uid']}").json()
    assert conv["mode"] == "session"
    assert conv["session"]["session_uid"] == started["session_uid"]
    # элемент doing после старта (SessionStarted)
    fresh = client.get(f"/api/courses/{course2['uid']}").json()
    assert fresh["items"][0]["status"] == "doing"


def test_today_attention_sources(client, container):
    """Источники в обработке/с ошибкой попадают в sources_attention."""
    container.library.add_source("web", "В обработке", url="https://x/1")
    with container.uow() as uow:
        from app.modules.library.infra.tables import sources as sources_t

        uow.session.execute(
            sources_t.update().where(sources_t.c.title == "В обработке").values(status="processing")
        )
    out = client.get("/api/today").json()
    assert any(s["status"] == "processing" for s in out["sources_attention"])


def test_today_reading_has_kind_for_link(client, container):
    """Чтение несёт kind источника — «Читать дальше» ведёт книгу в PDF-ридер,
    видео/статью — в главу, а не в 404 (B-012)."""
    src = _mk_source_with_chapters(container)
    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})

    out = client.get("/api/today").json()
    assert out["reading"][0]["kind"] == "book"


def test_today_reading_video_kind_not_fake_book(client, container):
    """kind берётся из источника, без дефолта book: видео остаётся видео,
    неизвестный тип не уводит в PDF-ридер (B-012 fix)."""
    src = _mk_source_with_chapters(container, kind="video")
    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})

    out = client.get("/api/today").json()
    assert out["reading"][0]["kind"] == "video"


def test_course_items_carry_source_kind(client, container):
    """Элементы курса с источником несут kind: «Читать» строит ссылку по типу
    (книга → /read, видео → глава), а не в 404 (B-012 fix)."""
    src = _mk_source_with_chapters(container, kind="video")
    course = client.post(
        "/api/courses",
        json={"topic": "видео-курс", "items": [{"item_type": "chapter", "source": src["uid"], "chapter": 2}]},
    ).json()

    full = client.get(f"/api/courses/{course['uid']}").json()
    item = full["items"][0]
    assert item["kind"] == "video" and item["source_uid"] == src["uid"]

    book_course = client.post(
        "/api/courses",
        json={
            "topic": "книга-курс",
            "items": [
                {"item_type": "chapter", "source": _mk_source_with_chapters(container)["uid"], "chapter": 1}
            ],
        },
    ).json()
    book_item = client.get(f"/api/courses/{book_course['uid']}").json()["items"][0]
    assert book_item["kind"] == "book"


def test_today_reading_skips_cursor_beyond_total(client, container):
    """Залипшая active с курсором за последней главой (пересборка глав)
    не висит в «Продолжить» — вести больше некуда (B-012)."""
    src = _mk_source_with_chapters(container)
    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})
    with container.uow() as uow:
        uow.session.execute(
            activities_table.update()
            .where(activities_table.c.source_id == src["id"])
            .values(cursor_chapter=99)
        )

    out = client.get("/api/today").json()
    assert out["reading"] == []
