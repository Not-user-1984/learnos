"""B-004: петля обучения — finish закрывает элемент курса, повторение заводится,
block_sources заполняются, «прочитал сам» засчитывается как read."""

import json

from app.llm.providers.fake import FakeTurn
from app.modules.library.infra.tables import chapters as chapters_table


def _mk_source_with_chapters(container, n: int = 3) -> dict:
    """Источник-книга с n главами (главы — напрямую: процессинг тут не важен)."""
    src = container.library.add_source("book", "Книга петли", url=None)
    with container.uow() as uow:
        for idx in range(1, n + 1):
            uow.session.execute(
                chapters_table.insert().values(
                    source_id=src["id"],
                    idx=idx,
                    title=f"Глава {idx}",
                    path=f"/tmp/loop-ch{idx}.md",
                    tokens_est=100,
                )
            )
    return src


def _course_with_chapters(client, src: dict, chapters: list[int]) -> dict:
    return client.post(
        "/api/courses",
        json={
            "topic": "петля",
            "items": [{"item_type": "chapter", "source": src["uid"], "chapter": c} for c in chapters],
        },
    ).json()


def _to_debrief(client, ref: str) -> None:
    """Провести сессию по стейт-машине до debrief (с фейнман-гейтом)."""
    for ev in ("ask", "answer", "theory_done", "go_practice", "practice_done"):
        r = client.post(f"/api/sessions/{ref}/advance", json={"event": ev, "payload": {}})
        assert r.status_code == 200, r.text


def _writer_turn() -> FakeTurn:
    return FakeTurn(
        text=json.dumps(
            {
                "title": "Урок по главе",
                "summary": "итог",
                "theses": ["тезис"],
                "concepts": [{"term": "понятие", "definition": "определение"}],
                "category_suggestion": "infra/kubernetes",
            },
            ensure_ascii=False,
        )
    )


def test_finish_session_closes_item_and_schedules_review(client, container, fake_llm):
    """Финиш сессии по элементу курса: элемент done, курс active, блок с block_sources,
    review_item с due_at = завтра (в очереди сегодня его нет)."""
    src = _mk_source_with_chapters(container)
    course = _course_with_chapters(client, src, [1, 2])
    item = course["items"][0]
    assert item["status"] == "todo"

    ses = client.post(f"/api/courses/{course['uid']}/items/{item['id']}/session", json={}).json()
    assert ses["course_item_id"] == item["id"]

    # SessionStarted → элемент doing, курс active
    fresh = client.get(f"/api/courses/{course['uid']}").json()
    assert [i["status"] for i in fresh["items"]] == ["doing", "todo"]
    assert fresh["status"] == "active"

    _to_debrief(client, ses["session_uid"])
    fake_llm.queue(_writer_turn())
    fin = container.learning.finish_session(ses["session_uid"])
    assert fin["ok"] is True

    # SessionFinished → элемент done, курс active (второй элемент ещё todo)
    fresh = client.get(f"/api/courses/{course['uid']}").json()
    assert [i["status"] for i in fresh["items"]] == ["done", "todo"]
    assert fresh["status"] == "active"
    assert fresh["next_step"]["item_id"] == fresh["items"][1]["id"]

    # блок урока несёт источник и главу (block_sources) и активность
    block = container.knowledge.get_block(fin["block_uid"])
    assert any(s.source == src["uid"] and s.chapter == 1 for s in block.meta.sources)
    assert block.meta.activity_uid

    # повторение запланировано на завтра: total есть, сегодня в очереди его нет
    stats = client.get("/api/review/stats").json()
    assert stats["total"] >= 1
    assert stats["due_today"] == 0
    queue = client.get("/api/review/queue?limit=10").json()
    assert all(i["block_uid"] != fin["block_uid"] for i in queue)

    # повторное событие не дублирует review_item
    from app.modules.learning.events import SessionFinished

    container.review.on_session_finished(
        SessionFinished(session_uid=ses["session_uid"], block_uid=fin["block_uid"])
    )
    stats2 = client.get("/api/review/stats").json()
    assert stats2["total"] == stats["total"]


def test_mark_read_closes_item_as_read(client, container):
    """«Прочитал сам» → элемент read; единственный read-элемент делает курс done."""
    src = _mk_source_with_chapters(container, n=1)
    course = _course_with_chapters(client, src, [1])

    r = client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})
    assert r.status_code == 200, r.text

    fresh = client.get(f"/api/courses/{course['uid']}").json()
    assert fresh["items"][0]["status"] == "read"
    assert fresh["status"] == "done"
    assert fresh["items_done"] == 1


def test_chapter_closes_in_all_courses(client, container, fake_llm):
    """Сессия/чтение одной главы закрывает её элементы во всех курсах (риск из плана)."""
    src = _mk_source_with_chapters(container, n=1)
    course_a = _course_with_chapters(client, src, [1])
    course_b = _course_with_chapters(client, src, [1])

    r = client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})
    assert r.status_code == 200

    a = client.get(f"/api/courses/{course_a['uid']}").json()
    b = client.get(f"/api/courses/{course_b['uid']}").json()
    assert a["items"][0]["status"] == "read"
    assert b["items"][0]["status"] == "read"


def test_read_item_upgrades_to_done_by_session(client, container, fake_llm):
    """Прочитанная глава после сессии становится done (read → done)."""
    src = _mk_source_with_chapters(container, n=1)
    course = _course_with_chapters(client, src, [1])
    item = course["items"][0]

    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})
    assert client.get(f"/api/courses/{course['uid']}").json()["items"][0]["status"] == "read"

    ses = client.post(f"/api/courses/{course['uid']}/items/{item['id']}/session", json={}).json()
    _to_debrief(client, ses["session_uid"])
    fake_llm.queue(_writer_turn())
    container.learning.finish_session(ses["session_uid"])

    fresh = client.get(f"/api/courses/{course['uid']}").json()
    assert fresh["items"][0]["status"] == "done"


def test_legacy_course_backfills_status_on_read(client, container, fake_llm):
    """Старый курс (все элементы todo): фактически пройденная глава получает done
    при первом чтении — бэкфилл статусами без миграции данных."""
    src = _mk_source_with_chapters(container, n=1)
    course = _course_with_chapters(client, src, [1])

    # глава «фактически пройдена»: блок с block_sources по главе 1
    from app.modules.knowledge.domain import BlockDraft, BlockSource

    container.knowledge.save_block(
        BlockDraft(title="Старый конспект", sources=(BlockSource(source=src["uid"], chapter=1),))
    )

    fresh = client.get(f"/api/courses/{course['uid']}").json()
    assert fresh["items"][0]["status"] == "done"
    assert fresh["items_done"] == 1
