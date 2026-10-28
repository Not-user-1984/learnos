"""Сценарии единого входа (T-039): интент сообщения → директива агенту, сценарий-бейдж разговора."""

import pytest

from app.llm.providers.fake import FakeTurn
from tests.api.test_sse import parse_sse


def _send(client, uid: str, content: str = "поехали", **extra) -> list[tuple[str, dict]]:
    """Отправить сообщение и вернуть SSE-события."""
    with client.stream(
        "POST", f"/api/conversations/{uid}/messages", json={"content": content, **extra}
    ) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    return parse_sse(raw)


def _system_prompt(fake_llm) -> str:
    """Системное сообщение первого запроса агента: промпт + блок «Контекст» с директивой."""
    _, request = fake_llm.requests[0]
    return request.messages[0].content


def _with_activity(client) -> dict:
    """Разговор с активностью-источником (для сценариев, где нужна сессия по главе)."""
    src = client.post("/api/sources", json={"kind": "book", "title": "Книга тестов"}).json()
    act = client.post("/api/activities", json={"source": src["uid"]}).json()
    return {"activity": act["uid"], "chapter": 1}


@pytest.mark.parametrize(
    "intent, marker",
    [
        ("review", "быстрый разбор"),
        ("study", "изучение источника"),
        ("session", "сессия-урок"),
        ("quote", "разбор фрагмента"),
        ("tune", "настройка агента"),
        ("reinforce", "закрепление пройденного"),
    ],
)
def test_intent_directive_reaches_root_agent(client, fake_llm, intent, marker):
    """Интент первого сообщения превращается сервером в директиву в system_extra;
    видимый текст сообщения остаётся пользователю."""
    fake_llm.queue(FakeTurn(text="готово"), FakeTurn(text="заголовок"))
    body = {} if intent != "session" else _with_activity(client)
    conv = client.post("/api/conversations", json=body).json()
    assert conv["mode"] == "root"

    events = _send(client, conv["uid"], intent=intent)

    assert [name for name, _ in events][-1] == "done"
    prompt = _system_prompt(fake_llm)
    assert f"Сценарий «{marker}»" in prompt


def test_unknown_intent_rejected(client):
    """Неизвестный код интета отбивается на схеме сообщения (422)."""
    conv = client.post("/api/conversations", json={}).json()
    resp = client.post(f"/api/conversations/{conv['uid']}/messages", json={"content": "x", "intent": "bogus"})
    assert resp.status_code == 422


def test_session_intent_creates_bound_session(client, fake_llm):
    """Кнопка «Сессия» у главы: root-разговор + intent=session — сервер сам создаёт
    сессию, привязанную к разговору; SSE-событие session и сценарий в бейдже."""
    src = client.post("/api/sources", json={"kind": "book", "title": "Книга тестов"}).json()
    act = client.post("/api/activities", json={"source": src["uid"]}).json()
    conv = client.post("/api/conversations", json={"activity": act["uid"], "chapter": 2}).json()
    assert conv["mode"] == "root"

    fake_llm.queue(FakeTurn(text="Начинаем урок."), FakeTurn(text="заголовок"))
    events = _send(client, conv["uid"], "начнём", intent="session")

    session_events = [d for name, d in events if name == "session"]
    assert session_events and session_events[0]["state"] == "theory"

    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    assert fresh["mode"] == "root"
    assert fresh["session"]["state"] == "theory"
    assert fresh["scenario"] == "Сессия · глава 2"


def test_conversation_scenario_labels(client):
    """Сценарий-бейдж: старые режимы как есть, root — по данным разговора."""
    video_src = client.post("/api/sources", json={"kind": "video", "title": "Видео"}).json()
    video_act = client.post("/api/activities", json={"source": video_src["uid"]}).json()
    book_src = client.post("/api/sources", json={"kind": "book", "title": "Книга"}).json()
    book_act = client.post("/api/activities", json={"source": book_src["uid"]}).json()

    uids = {
        "plain": client.post("/api/conversations", json={}).json()["uid"],
        "block": client.post("/api/conversations", json={"focus_block": "blk_x"}).json()["uid"],
        "video": client.post("/api/conversations", json={"activity": video_act["uid"]}).json()["uid"],
        "chapter": client.post("/api/conversations", json={"activity": book_act["uid"], "chapter": 3}).json()[
            "uid"
        ],
        "quick": client.post("/api/conversations", json={"mode": "quick"}).json()["uid"],
    }
    expected = {
        "plain": "Разговор",
        "block": "Разбор блока",
        "video": "Разбор видео",
        "chapter": "Разбор · глава 3",
        "quick": "Быстрый разбор",
    }
    for key, uid in uids.items():
        detail = client.get(f"/api/conversations/{uid}").json()
        assert detail["scenario"] == expected[key], key

    listed = {c["uid"]: c["scenario"] for c in client.get("/api/conversations").json()}
    assert listed[uids["plain"]] == "Разговор"
    assert listed[uids["quick"]] == "Быстрый разбор"


def test_root_has_session_and_review_tools(container):
    """Root ведёт сессию (интент «session») и повторения (интент «reinforce») сам."""
    tools = container.agent_registry.get("root").tools
    assert {"start_session", "advance", "practice_step", "finish_session"} <= tools
    assert {"get_review_queue", "answer_review", "mark_chapter_done"} <= tools
