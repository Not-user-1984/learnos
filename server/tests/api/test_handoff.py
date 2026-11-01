"""T-050 Э4: handoff — интент передаёт разговор специалисту, специалист ведёт сам."""

from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from tests.api.test_sse import parse_sse

TUTOR_MARK = "тытор сессии-урока"  # фрагмент уникальной первой строки промпта session_tutor


def _stream(client, uid: str, content: str, intent: str | None = None) -> list:
    payload = {"content": content}
    if intent:
        payload["intent"] = intent
    with client.stream("POST", f"/api/conversations/{uid}/messages", json=payload) as resp:
        raw = "".join(resp.iter_text())
    return parse_sse(raw)


def _post(client, uid: str, content: str, intent: str | None = None) -> dict:
    payload = {"content": content}
    if intent:
        payload["intent"] = intent
    r = client.post(f"/api/conversations/{uid}/messages", json=payload)
    assert r.status_code == 200, r.text
    events = parse_sse(r.text)
    return events


def test_intent_review_hands_off_to_quick_reviewer(container, client, fake_llm):
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(FakeTurn(text="Разбираю главу"))
    events = _post(client, conv["uid"], "разбери главу", intent="review")

    handoffs = [d for name, d in events if name == "handoff"]
    assert handoffs and handoffs[0]["agent"] == "quick_reviewer"
    detail = client.get(f"/api/conversations/{conv['uid']}").json()
    assert detail["active_agent"] == "quick_reviewer"


def _conv_with_activity(container, client) -> dict:
    """Разговор, привязанный к активности источника (сценарий «Сессия» у главы)."""
    src = container.library.add_source("video", "Видео-урок", url="https://youtu.be/hndof123")
    act = container.learning.start_activity(src["uid"])
    return client.post("/api/conversations", json={"mode": "root", "activity": act["uid"]}).json()


def test_specialist_keeps_leading_next_turns(container, client, fake_llm):
    """Со второго хода разговор ведёт специалист — промпт его, root не вмешивается (R-13)."""
    conv = _conv_with_activity(container, client)
    fake_llm.queue(FakeTurn(text="Передаю тьютору"))
    _post(client, conv["uid"], "хочу сессию по главе", intent="session")

    fake_llm.queue(FakeTurn(text="Начинаем урок"))
    _post(client, conv["uid"], "поехали")

    # агентские запросы отличаем от fast-заголовочника по наличию схем инструментов
    agent_reqs = [r for r in fake_llm.requests if r[1].tools]
    system = agent_reqs[-1][1].messages[0].content
    assert "сессии-урока" in system  # промпт session_tutor ведёт
    assert client.get(f"/api/conversations/{conv['uid']}").json()["active_agent"] == "session_tutor"


def test_handoff_tool_switches_agent(container, client, fake_llm):
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("handoff", agent="session_tutor", reason="урок")]),
        FakeTurn(text="Передал тьютору"),
    )
    events = _post(client, conv["uid"], "проведи урок")

    ends = {d["name"]: d for name, d in events if name == "tool_end"}
    assert ends["handoff"]["ok"] is True
    assert client.get(f"/api/conversations/{conv['uid']}").json()["active_agent"] == "session_tutor"


def test_handoff_back_returns_root(container, client, fake_llm):
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(FakeTurn(text="старт"))
    _post(client, conv["uid"], "разбор", intent="review")  # quick_reviewer ведёт

    # сам специалист возвращает root (инструмент доступен из любого агента)
    result = container.tools.call(
        "handoff_back",
        {},
        __import__("app.kernel.tools.spec", fromlist=["ToolContext"]).ToolContext(
            channel="agent", conversation_uid=conv["uid"], agent_name="quick_reviewer"
        ),
    )
    assert result["ok"] is True
    assert client.get(f"/api/conversations/{conv['uid']}").json()["active_agent"] == "root"


def test_handoff_unknown_agent_clear_error(container, client, fake_llm):
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("handoff", agent="nope")]),
        FakeTurn(text="Такого нет"),
    )
    events = _post(client, conv["uid"], "позови кого-нибудь")
    ends = {d["name"]: d for name, d in events if name == "tool_end"}
    assert ends["handoff"]["ok"] is False
    assert client.get(f"/api/conversations/{conv['uid']}").json()["active_agent"] is None


def test_legacy_mode_without_active_agent_unchanged(container, client, fake_llm):
    """Старые разговоры (mode=quick и др.) ведутся по mode, без active_agent (легаси)."""
    conv = client.post("/api/conversations", json={"mode": "quick"}).json()
    fake_llm.queue(FakeTurn(text="разбор"))
    _post(client, conv["uid"], "разбери")

    detail = client.get(f"/api/conversations/{conv['uid']}").json()
    assert detail["active_agent"] is None
    agent_reqs = [r for r in fake_llm.requests if r[1].tools]
    system = agent_reqs[-1][1].messages[0].content
    assert "разбор источника" in system.lower()  # quick_reviewer по mode, как раньше
