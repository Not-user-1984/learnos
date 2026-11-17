"""B-013: место чтения книги в активности и «Записать главу в базу» из разговора главы."""

import json

import pytest

from app.kernel.errors import InvalidState
from app.llm.providers.fake import FakeTurn
from app.modules.library.infra.tables import chapters as chapters_table


def _mk_source_with_chapters(container, kind: str = "book", n: int = 3) -> dict:
    src = container.library.add_source(kind, f"Книга {kind}", url=None)
    with container.uow() as uow:
        for idx in range(1, n + 1):
            uow.session.execute(
                chapters_table.insert().values(
                    source_id=src["id"],
                    idx=idx,
                    title=f"Глава {idx}",
                    path=f"/tmp/b013-{src['uid']}-ch{idx}.md",
                    tokens_est=100,
                )
            )
    return src


# --- место чтения (position) ---


def test_position_stored_and_returned(client, container):
    """POST /activities/{uid}/position сохраняет главу+страницу; курсор не трогает."""
    src = _mk_source_with_chapters(container)
    act = container.learning.start_activity(src["uid"])

    out = client.post(f"/api/activities/{act['uid']}/position", json={"chapter": 3, "page": 42}).json()

    assert out["ok"] and out["position_chapter"] == 3 and out["position_page"] == 42
    fresh = client.get(f"/api/activities/{act['uid']}").json()
    assert fresh["position_chapter"] == 3 and fresh["position_page"] == 42
    # место ≠ прогресс: курсор остаётся на первой главе
    assert fresh["cursor_chapter"] == 1


def test_position_follows_progress(client, container):
    """mark_read двигает и курсор, и место — «Читать дальше» после главы ведит дальше."""
    src = _mk_source_with_chapters(container)
    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 2})

    fresh = client.get("/api/activities").json()[0]
    assert fresh["cursor_chapter"] == 3
    assert fresh["position_chapter"] == 3 and fresh["position_page"] is None


def test_today_reading_opens_position(client, container):
    """«Сегодня» отдаёт место чтения: глава 3, страница 5 — не курсор."""
    src = _mk_source_with_chapters(container)
    act = container.learning.start_activity(src["uid"])
    client.post(f"/api/activities/{act['uid']}/position", json={"chapter": 3, "page": 5})

    out = client.get("/api/today").json()
    r = out["reading"][0]
    assert r["position_chapter"] == 3 and r["position_page"] == 5 and r["cursor_chapter"] == 1


# --- «Записать главу в базу» (глава-сессия check → done) ---


def test_commit_creates_chapter_session(client, container):
    """commit-роут: get-or-create разговора главы + лёгкая сессия kind=chapter в check."""
    src = _mk_source_with_chapters(container)

    out = client.post(f"/api/sources/{src['uid']}/chapters/2/conversation/commit").json()

    assert out["kind"] == "chapter" and out["state"] == "check"
    assert out["conversation_uid"].startswith("cnv_") and out["session_uid"].startswith("ses_")

    # повторный commit идемпотентен: та же сессия, без дублей
    again = client.post(f"/api/sources/{src['uid']}/chapters/2/conversation/commit").json()
    assert again["session_uid"] == out["session_uid"]


def test_commit_without_answer_rejected(client, container):
    """Фейнман-гейт: без единого ответа пользователя главу в базу не записать."""
    src = _mk_source_with_chapters(container)
    out = client.post(f"/api/sources/{src['uid']}/chapters/1/conversation/commit").json()

    with pytest.raises(InvalidState, match="перескажи суть"):
        container.learning.finish_chapter_for_conversation(out["conversation_uid"])


def test_commit_saves_verified_block_with_source(client, container, fake_llm):
    """Мини-фейнман ask→answer → commit: блок verified с block_sources и событием сессии."""
    src = _mk_source_with_chapters(container)
    out = client.post(f"/api/sources/{src['uid']}/chapters/2/conversation/commit").json()
    ses = out["session_uid"]

    container.learning.advance(ses, "ask", {"question": "Перескажи суть главы 2 своими словами"})
    container.learning.advance(ses, "answer", {"answer": "Суть главы 2 — вот такая, своими словами"})

    # block_writer (structured) — заготовленный ответ фейкового LLM
    fake_llm.queue(
        FakeTurn(
            text=json.dumps(
                {
                    "title": "Глава 2: суть",
                    "summary": "Что дала глава 2 пользователю",
                    "theses": ["тезис главы"],
                    "concepts": [],
                    "practice": [],
                    "weak_spots": [],
                    "category_suggestion": "Книги/Тест",
                },
                ensure_ascii=False,
            )
        )
    )

    result = container.learning.finish_chapter_for_conversation(out["conversation_uid"])

    assert result["ok"] and result["block_uid"].startswith("blk_")
    meta = container.knowledge.get_block(result["block_uid"]).meta
    assert meta.verified is True
    assert any(s.chapter == 2 and s.source == src["uid"] for s in meta.sources)

    # сессия закрыта, курсор догнал главу, повторение заведено (событие как у сессии)
    st = container.learning.get_session_state(ses)
    assert st["status"] == "finished" and st["state"] == "done"
    act = client.get("/api/activities").json()[0]
    assert act["cursor_chapter"] >= 3
    # review_item заводится с due_at=завтра — в очереди дня ещё нет, в total есть
    assert client.get("/api/review/stats").json()["total"] >= 1


def test_lesson_finish_still_requires_debrief(client, container):
    """Обычная сессия-урок от короткого пути не зависит: check ≠ debrief (машина не тронута)."""
    course = client.post("/api/courses", json={"topic": "проверка машины"}).json()
    ses = client.post("/api/sessions", json={"course_id": course["id"]}).json()
    container.learning.advance(ses["session_uid"], "answer", {"answer": "ответ"})

    with pytest.raises(InvalidState, match="debrief"):
        container.learning.finish_session(ses["session_uid"])
