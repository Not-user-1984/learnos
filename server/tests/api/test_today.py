"""B-005: дашборд «Сегодня» и старт сессии по элементу курса из UI."""

from app.modules.library.infra.tables import chapters as chapters_table


def _mk_source_with_chapters(container, n: int = 3) -> dict:
    src = container.library.add_source("book", "Книга дня", url=None)
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
