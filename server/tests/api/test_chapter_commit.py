"""B-013: место чтения книги в активности и «Записать главу в базу» из разговора главы."""

import json

import pytest

from app.kernel.errors import InvalidState
from app.llm.providers.fake import FakeTurn
from app.modules.library.infra.tables import chapters as chapters_table


def _writer_turn() -> FakeTurn:
    return FakeTurn(
        text=json.dumps(
            {
                "title": "Глава: суть",
                "summary": "с",
                "theses": ["тезис главы"],
                "concepts": [],
                "practice": [],
                "weak_spots": [],
                "open_questions": [],
                "links": [],
                "tags": [],
                "category_suggestion": "Книги/Тест",
            },
            ensure_ascii=False,
        )
    )


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


# --- раунд 2: замечания ревью B-013 ---


def test_chapter_out_of_range_rejected(client, container):
    """Разговор/commit по несуществующей главе — 404, курсор и сессии не трогаются (fix п.1)."""
    src = _mk_source_with_chapters(container)  # 3 главы
    for path in (
        f"/api/sources/{src['uid']}/chapters/99/conversation",
        f"/api/sources/{src['uid']}/chapters/99/conversation/commit",
    ):
        assert client.post(path).status_code == 404, path
    assert client.get("/api/activities").json() == []


def test_chapter_session_rejects_foreign_session(client, container):
    """Активная сессия-урок в разговоре главы блокирует «Записать в базу» (fix п.2)."""
    import pytest

    src = _mk_source_with_chapters(container)
    conv = container.chat.chapter_conversation(src["uid"], 1)
    act = container.learning.start_activity(src["uid"])
    info = container.chat.conversation_info(conv["uid"])
    container.learning.start_session(activity_ref=act["uid"], conversation_id=info["id"])

    with pytest.raises(InvalidState, match="сессия-урок"):
        container.learning.start_chapter_session(conv["uid"])


def test_repeated_commit_returns_same_block(client, container, fake_llm):
    """Повторная запись уже записанной главы — тот же block_uid, без дубля (fix п.3)."""
    src = _mk_source_with_chapters(container)
    out = client.post(f"/api/sources/{src['uid']}/chapters/2/conversation/commit").json()
    ses = out["session_uid"]
    container.learning.advance(ses, "ask", {"question": "суть?"})
    container.learning.advance(ses, "answer", {"answer": "вот такая"})
    fake_llm.queue(_writer_turn())
    first = container.learning.finish_chapter_for_conversation(out["conversation_uid"])
    assert first["ok"] and not first.get("already_committed")

    # повторный старт не создаёт вторую сессию, повторный коммит — тот же блок
    again_session = container.learning.start_chapter_session(out["conversation_uid"])
    assert again_session["status"] == "finished" and again_session["session_uid"] == ses
    second = container.learning.finish_chapter_for_conversation(out["conversation_uid"])
    assert second.get("already_committed") is True
    assert second["block_uid"] == first["block_uid"]
    blocks = container.knowledge.list_blocks(source=src["uid"])
    assert len(blocks) == 1


def test_position_survives_backward_mark_read(client, container):
    """mark-read позади курсора не затирает место чтения; прогресс двигает место (fix п.4)."""
    src = _mk_source_with_chapters(container)
    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 2})  # курсор 3
    act = client.get("/api/activities").json()[0]
    client.post(f"/api/activities/{act['uid']}/position", json={"chapter": 3, "page": 5})

    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 1})  # назад
    fresh = client.get("/api/activities").json()[0]
    assert fresh["cursor_chapter"] == 3
    assert fresh["position_chapter"] == 3 and fresh["position_page"] == 5  # не затёрто

    client.post("/api/activities/mark-read", json={"source": src["uid"], "chapter": 3})  # вперёд
    fresh = client.get("/api/activities").json()[0]
    assert fresh["cursor_chapter"] == 4  # total+1 → done
    assert fresh["position_chapter"] == 4 and fresh["position_page"] is None


def test_finish_chapter_session_syncs_position(client, container, fake_llm):
    """Финиш главы-сессии синхронизирует место с курсором (fix п.4)."""
    src = _mk_source_with_chapters(container)
    act = container.learning.start_activity(src["uid"])
    container.learning.set_position(act["uid"], 1, 9)  # читал главу 1, страницу 9
    out = client.post(f"/api/sources/{src['uid']}/chapters/1/conversation/commit").json()
    container.learning.advance(out["session_uid"], "ask", {"question": "суть?"})
    container.learning.advance(out["session_uid"], "answer", {"answer": "такая"})
    fake_llm.queue(_writer_turn())
    container.learning.finish_chapter_for_conversation(out["conversation_uid"])

    fresh = client.get("/api/activities").json()[0]
    assert fresh["cursor_chapter"] == 2
    assert fresh["position_chapter"] == 2 and fresh["position_page"] is None


def test_set_position_validates_bounds(client, container):
    """Место чтения: глава ≤ total, страница ≥ 1 — иначе 422 (fix п.5)."""
    src = _mk_source_with_chapters(container)  # 3 главы
    act = container.learning.start_activity(src["uid"])
    assert (
        client.post(f"/api/activities/{act['uid']}/position", json={"chapter": 99, "page": 1}).status_code
        == 422
    )
    assert (
        client.post(f"/api/activities/{act['uid']}/position", json={"chapter": 2, "page": 0}).status_code
        == 422
    )
    ok = client.post(f"/api/activities/{act['uid']}/position", json={"chapter": 3, "page": 7})
    assert ok.status_code == 200
