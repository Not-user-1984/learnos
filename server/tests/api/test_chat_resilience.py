"""T-041 Устойчивость ответа: обрыв SSE-читателя, startup-хук прерванных запусков,
agent_state в detail, resume последнего user-сообщения."""

import datetime
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from tests.api.test_sse import parse_sse


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _insert_unanswered_user(container, uid: str, content: str) -> None:
    """Последнее user-сообщение без ответа — как после гибели генерации."""
    with container.uow() as uow:
        conv_id = uow.session.execute(
            text("SELECT id FROM conversations WHERE uid=:u"), {"u": uid}
        ).scalar_one()
        uow.session.execute(
            text(
                "INSERT INTO messages (conversation_id, role, content, cards_json, created_at) "
                "VALUES (:c, 'user', :content, '[]', :now)"
            ),
            {"c": conv_id, "content": content, "now": _now_iso()},
        )


def _insert_run(container, uid: str, status: str, *, agent: str = "root") -> None:
    """Запуск в agent_runs напрямую — след живой или прерванной генерации."""
    with container.uow() as uow:
        uow.session.execute(
            text(
                "INSERT INTO agent_runs (agent, provider, model, conversation_uid, status, steps, "
                "tool_calls, input_tokens, output_tokens, duration_ms, error, parent_run_id, created_at) "
                "VALUES (:agent, 'fake', 'fake-model', :uid, :status, 0, 0, 0, 0, 0, NULL, NULL, :now)"
            ),
            {"agent": agent, "uid": uid, "status": status, "now": _now_iso()},
        )


def _wait_for_assistant(client, uid: str, timeout: float = 10.0) -> dict | None:
    """Дождаться, пока фоновая генерация сохранит ответ (независимо от читателя)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        fresh = client.get(f"/api/conversations/{uid}").json()
        saved = next((m for m in fresh["messages"] if m["role"] == "assistant"), None)
        if saved:
            return saved
        time.sleep(0.1)
    return None


def test_sse_reader_disconnect_does_not_lose_reply(client, fake_llm):
    """Обрыв SSE-читателя посреди стрима: прокачка живёт в фоновой задаче и
    дорабатывает ответ — он сохраняется в БД, хотя клиент ушёл."""
    words = " ".join(f"слово{i}" for i in range(12))
    fake_llm.queue(FakeTurn(text=words, delay=0.08))
    conv = client.post("/api/conversations", json={"mode": "root", "title": "обрыв"}).json()

    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "вопрос"}
    ) as resp:
        broke_mid_stream = False
        for line in resp.iter_lines():
            if line.startswith("data:") and "слово0" in line:
                broke_mid_stream = True
                break
        assert broke_mid_stream  # ушли до done, ответ ещё генерировался

    saved = _wait_for_assistant(client, conv["uid"])
    assert saved is not None, "ответ должен был сохраниться после обрыва читателя"
    assert saved["content"] == words + " "


def test_startup_marks_stale_running_interrupted(rest_app, container):
    """Рестарт процесса помечает зависшие running → interrupted; detail отдаёт
    agent_state для баннера «генерация прервана»."""
    with TestClient(rest_app) as tc:
        conv = tc.post("/api/conversations", json={"mode": "root", "title": "видео"}).json()
    uid = conv["uid"]
    _insert_unanswered_user(container, uid, "добавь видео")
    _insert_run(container, uid, "running")  # погиб вместе с процессом

    # «процесс перезапустили»: новый lifespan закрывает зависшие запуски
    with TestClient(rest_app) as tc:
        with container.uow() as uow:
            row = uow.session.execute(
                text("SELECT status, error FROM agent_runs WHERE conversation_uid=:u"), {"u": uid}
            ).first()
        assert row.status == "interrupted"
        assert row.error == "процесс перезапущен"

        state = tc.get(f"/api/conversations/{uid}").json()["agent_state"]
        assert state["working"] is False
        assert state["runs"] == []
        assert state["interrupted"] is True


def test_send_message_while_busy_is_409_without_duplicate(client, container):
    """BUG-001: сообщение в занятый разговор — честный 409 до стрима; сообщение-дубль
    не сохраняется (раньше user-строка вставлялась до проверки занятости)."""
    conv = client.post("/api/conversations", json={"mode": "root", "title": "занят"}).json()
    uid = conv["uid"]
    _insert_unanswered_user(container, uid, "первый вопрос")
    _insert_run(container, uid, "running")  # генерация идёт (независимо от нашей вкладки)

    before = client.get(f"/api/conversations/{uid}").json()["messages"]
    r = client.post(f"/api/conversations/{uid}/messages", json={"content": "Да — делай"})
    assert r.status_code == 409
    assert "уже работает" in r.json()["message"]

    after = client.get(f"/api/conversations/{uid}").json()["messages"]
    assert [m["content"] for m in after] == [m["content"] for m in before]  # дубля нет


def test_agent_state_working_during_generation(rest_app, container, fake_llm):
    """Пока генерация идёт, detail отдаёт working=True и живой запуск с прогрессом
    (steps/tool_calls пишутся инкрементально по ходу).

    TestClient буферизует SSE-ответ, поэтому середину генерации наблюдает отдельный
    клиент в своём потоке: опрашивает detail, пока основной клиент держит стрим.
    """
    fake_llm.queue(
        FakeTurn(text="смотрю каталог", tool_calls=[FakeLLMProvider.call("list_agents")], delay=0.1),
        FakeTurn(text=" ".join(f"хвост{i}" for i in range(30)), delay=0.1),
    )
    conv_holder: dict = {}
    seen: dict = {}
    watcher_ready = threading.Event()
    stop = threading.Event()

    def watcher() -> None:
        with TestClient(rest_app) as tc2:
            watcher_ready.set()  # lifespan наблюдателя прошёл до старта генерации
            while not stop.is_set() and not seen:
                uid = conv_holder.get("uid")
                if uid:
                    state = tc2.get(f"/api/conversations/{uid}").json()["agent_state"]
                    runs = state.get("runs") or []
                    if state["working"] and runs and runs[0]["steps"] >= 1:
                        seen["state"] = state
                time.sleep(0.05)

    thread = threading.Thread(target=watcher)
    thread.start()
    assert watcher_ready.wait(timeout=10)
    try:
        with TestClient(rest_app) as tc:
            conv = tc.post("/api/conversations", json={"mode": "root", "title": "работа"}).json()
            conv_holder["uid"] = conv["uid"]
            with tc.stream(
                "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "вопрос"}
            ) as resp:
                raw = "".join(resp.iter_text())
        assert parse_sse(raw)[-1][0] == "done"
    finally:
        stop.set()
        thread.join(timeout=15)

    state = seen.get("state")
    assert state, "наблюдатель должен был поймать живую генерацию"
    assert [r["agent"] for r in state["runs"]] == ["root"]
    assert state["runs"][0]["tool_calls"] == 1
    assert state["runs"][0]["started_at"]
    # BUG-003: чем запуск занят прямо сейчас — label текущего инструмента
    assert state["runs"][0]["current"] == "Каталог агентов"

    # после завершения генерации working гаснет
    with TestClient(rest_app) as tc:
        final = tc.get(f"/api/conversations/{conv['uid']}").json()
    assert final["agent_state"]["working"] is False
    assert any(m["role"] == "assistant" for m in final["messages"])


def test_resume_completes_last_user_message(client, fake_llm, container):
    """Resume дорабатывает последний user-message: ответ генерируется заново,
    сообщение пользователя не дублируется."""
    fake_llm.queue(FakeTurn(text="Ответ восстановлен."), FakeTurn(text="заголовок"))
    conv = client.post("/api/conversations", json={"mode": "root"}).json()
    uid = conv["uid"]
    _insert_unanswered_user(container, uid, "добавь видео")
    _insert_run(container, uid, "interrupted")

    with client.stream("POST", f"/api/conversations/{uid}/resume") as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert "user_saved" not in names  # дубля user-сообщения нет
    assert names[-1] == "done"

    fresh = client.get(f"/api/conversations/{uid}").json()
    user_msgs = [m["content"] for m in fresh["messages"] if m["role"] == "user"]
    assert user_msgs == ["добавь видео"]
    assistant = next(m for m in fresh["messages"] if m["role"] == "assistant")
    assert assistant["content"] == "Ответ восстановлен. "

    # история ушла в LLM с user-сообщением в хвосте
    roles = [m.role for m in fake_llm.requests[-1][1].messages]
    assert roles[-1] == "user"

    # прерывание закрыто: баннер гаснет
    assert fresh["agent_state"]["interrupted"] is False


def test_resume_conflicts(client, container):
    """Resume конфликтует честно: нечего дописывать (409) и агент уже работает (409)."""
    conv = client.post("/api/conversations", json={"mode": "root", "title": "конфликт"}).json()
    uid = conv["uid"]

    # нет ни одного сообщения — продолжать нечего
    assert client.post(f"/api/conversations/{uid}/resume").status_code == 409

    # живой running-запуск — генерация уже идёт
    _insert_unanswered_user(container, uid, "вопрос")
    _insert_run(container, uid, "running")
    r = client.post(f"/api/conversations/{uid}/resume")
    assert r.status_code == 409
    assert "уже работает" in r.json()["message"]

    # ответ уже есть — продолжать нечего
    with container.uow() as uow:
        uow.session.execute(text("UPDATE agent_runs SET status='ok' WHERE conversation_uid=:u"), {"u": uid})
        conv_id = uow.session.execute(
            text("SELECT id FROM conversations WHERE uid=:u"), {"u": uid}
        ).scalar_one()
        uow.session.execute(
            text(
                "INSERT INTO messages (conversation_id, role, content, cards_json, created_at) "
                "VALUES (:c, 'assistant', 'готово', '[]', :now)"
            ),
            {"c": conv_id, "now": _now_iso()},
        )
    r = client.post(f"/api/conversations/{uid}/resume")
    assert r.status_code == 409
    assert "нечего" in r.json()["message"]
