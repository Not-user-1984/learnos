"""SSE-эндпоинт чата: порядок событий, дельты, сохранение ответа, стоп."""

import json

from app.llm.providers.fake import FakeLLMProvider, FakeTurn


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    """Разобрать SSE-текст в список пар (event, data)."""
    out: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = "", {}
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        out.append((event, data))
    return out


def test_free_chat_sse_stream(client, fake_llm):
    fake_llm.queue(
        FakeTurn(text="Привет! Как дела?"),
        FakeTurn(text="Разговор о приветствиях"),  # ответ для авто-заголовка (роль fast)
    )
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    uid = conv["uid"]

    with client.stream("POST", f"/api/conversations/{uid}/messages", json={"content": "привет"}) as resp:
        assert resp.status_code == 200
        # SSE-эндпоинт обязан отвечать text/event-stream
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    names = [name for name, _ in events]

    # user_saved раньше первой дельты; стрим завершается done
    assert names[0] == "user_saved"
    assert "delta" in names
    assert names[-1] == "done"
    assert names.index("user_saved") < names.index("delta")

    # дельты в сумме дают текст ответа (фейк добавляет пробел после каждого слова)
    deltas = "".join(data["text"] for name, data in events if name == "delta")
    assert deltas == "Привет! Как дела? "

    # авто-заголовок разговора пришёл отдельным событием
    titles = [data for name, data in events if name == "title"]
    assert titles and titles[0]["title"] == "Разговор о приветствиях"

    # done несёт id сохранённого сообщения ассистента
    done = [data for name, data in events if name == "done"][0]
    assert isinstance(done["message_id"], int)

    # сообщения сохранены в БД
    fresh = client.get(f"/api/conversations/{uid}").json()
    roles = {(m["role"], m["content"]) for m in fresh["messages"]}
    assert ("user", "привет") in roles
    assert ("assistant", "Привет! Как дела? ") in roles
    assert fresh["title"] == "Разговор о приветствиях"


def test_sse_error_event_on_invalid_conversation(client):
    """Несуществующий разговор: SSE-эндпоинт отвечает 200, ошибка уходит событием error."""
    with client.stream("POST", "/api/conversations/cnv_nope000/messages", json={"content": "привет"}) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    # при ошибке стрим заканчивается событием error (без done); ошибка приложения
    # несёт свой код (not_found/conflict), а не безликий internal
    assert [name for name, _ in events] == ["error"]
    error = events[0][1]
    assert error["error"] == "not_found"
    assert "не найден" in error["message"]


def test_stop_without_running_generation(client):
    """Stop для разговора без активной генерации — честный ok=false."""
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    r = client.post(f"/api/conversations/{conv['uid']}/stop")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "note": "нет активной генерации"}


def test_cancellation_token_unit():
    """Юнит-проверка токена отмены (стриминговый таймаут в тестах не таймим)."""
    from app.agent.spec import AgentCancelled, CancellationToken

    token = CancellationToken()
    token.raise_if_cancelled()  # не бросает
    token.cancel()
    try:
        token.raise_if_cancelled()
        raise AssertionError("ожидали AgentCancelled")
    except AgentCancelled:
        pass


def test_first_message_contains_user_role(client, fake_llm):
    """Первое сообщение нового разговора должно уходить в LLM с user-ролью.

    Раньше history была пуста и запрос состоял из одного system — z.ai отвечал 1214.
    """
    conv = client.post("/api/conversations", json={"mode": "free", "title": "первое"}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "привет"}
    ) as resp:
        for _ in resp.iter_lines():
            pass
    assert fake_llm.requests, "запрос к LLM должен был случиться"
    roles = [m.role for m in fake_llm.requests[-1][1].messages]
    assert "user" in roles


def test_research_flag_directive_hidden_from_chat(client, fake_llm):
    """research=true: директива уходит агенту в system_extra, в чате — только тема.

    Пользователь не должен видеть служебную простыню ни сообщением, ни в истории.
    """
    fake_llm.queue(FakeTurn(text="Нашёл три источника, топ-2 добавил."))
    conv = client.post("/api/conversations", json={"mode": "free", "title": "ресёрч"}).json()
    with client.stream(
        "POST",
        f"/api/conversations/{conv['uid']}/messages",
        json={"content": "Докер для начинающих", "research": True},
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    assert [name for name, _ in events][-1] == "done"

    # тема сохранилась как обычное сообщение юзера — без служебной простыни
    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    user_msgs = [m["content"] for m in fresh["messages"] if m["role"] == "user"]
    assert user_msgs == ["Докер для начинающих"]

    # директива и повышенный лимит шагов дошли до агента
    system = fake_llm.requests[-1][1].messages[0].content
    assert "ресёрч-цикл" in system
    assert "web_search" in system
    assert "torrent_fetch" in system  # подсказка про скилл закачек (T-029)
    # добавление источников — только по согласию через карточку offer_action (BUG-006)
    assert "offer_action" in system
    assert "НИЧЕГО не добавляй" in system


def test_quick_replies_card_in_sse_and_history(client, fake_llm):
    """offer_replies: карточка quick_replies доходит SSE-событием и сохраняется в ответе (T-045)."""
    fake_llm.queue(
        FakeTurn(
            tool_calls=[
                FakeLLMProvider.call("offer_replies", replies=["Дальше", "Подробнее", "Сессия по этой главе"])
            ]
        ),
        FakeTurn(text="Глава разобрана. Что дальше?"),
        FakeTurn(text="Разбор главы"),  # ответ для авто-заголовка (роль fast)
    )
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "погнали"}
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    assert [name for name, _ in events][-1] == "done"
    cards = [data for name, data in events if name == "card"]
    assert cards and cards[0]["card"]["type"] == "quick_replies"
    assert cards[0]["card"]["replies"] == ["Дальше", "Подробнее", "Сессия по этой главе"]

    # карточка сохранена в сообщении агента — кнопки кликабельны и в истории разговора
    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    assistant_cards = [
        c for m in fresh["messages"] if m["role"] == "assistant" for c in (m.get("cards") or [])
    ]
    assert any(c["type"] == "quick_replies" and "Дальше" in c["replies"] for c in assistant_cards)
