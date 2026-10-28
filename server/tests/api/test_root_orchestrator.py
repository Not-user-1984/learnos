"""Корневой агент-оркестратор: режим root, list_agents → run_agent, трейсы, карточка (T-035)."""

import json

from sqlalchemy import text

from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from tests.api.test_sse import parse_sse


def test_root_orchestrates_subagent(client, fake_llm, container):
    """Новый разговор по умолчанию root; сценарий list_agents → run_agent(repo_scout):
    ответ доходит, карточка итога в чате, трейсы связаны parent_run_id."""
    fake_llm.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("list_agents")]),
        FakeTurn(
            tool_calls=[
                FakeLLMProvider.call(
                    "run_agent", agent="repo_scout", task="Найди идеи в github.com/x/y для LearnOS"
                )
            ]
        ),
        FakeTurn(text="Идеи собраны: 3 приёма."),  # ответ субагента repo_scout
        FakeTurn(text="repo_scout разобрал репо: нашёл 3 идеи."),  # финал root
        FakeTurn(text="Разбор репо"),  # авто-заголовок (роль fast)
    )

    conv = client.post("/api/conversations", json={"title": "оркестратор"}).json()
    assert conv["mode"] == "root"  # дефолт новых разговоров

    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "разбери репо github.com/x/y"}
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    assert [name for name, _ in events][-1] == "done"

    # чипы: каталог затем запуск субагента
    starts = [(d["name"], d["label"]) for name, d in events if name == "tool_start"]
    assert ("list_agents", "Каталог агентов") in starts
    assert any(n == "run_agent" and "repo_scout" in label for n, label in starts)
    run_agent_end = next(d for name, d in events if name == "tool_end" and d["name"] == "run_agent")
    assert run_agent_end["ok"] is True
    assert "Идеи собраны" in run_agent_end["summary"]

    # карточка итога субагента пришла в поток и сохранилась в сообщении
    cards = [d["card"] for name, d in events if name == "card"]
    sub = next(c for c in cards if c["type"] == "subagent_result")
    assert sub["agent"] == "repo_scout"
    assert "github.com/x/y" in sub["task"]
    assert "Идеи собраны" in sub["summary"]

    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    assistant = next(m for m in fresh["messages"] if m["role"] == "assistant")
    assert "repo_scout" in assistant["content"]
    assert any(c["type"] == "subagent_result" for c in assistant["cards"])

    # трейсы в agent_runs связаны: запуск repo_scout указывает на запуск root
    with container.uow() as uow:
        runs = (
            uow.session.execute(text("SELECT id, agent, parent_run_id, status FROM agent_runs ORDER BY id"))
            .mappings()
            .all()
        )
    root_run = next(r for r in runs if r["agent"] == "root")
    sub_run = next(r for r in runs if r["agent"] == "repo_scout")
    assert sub_run["parent_run_id"] == root_run["id"]
    assert root_run["status"] == "ok" and sub_run["status"] == "ok"


def test_root_answers_simple_question_itself(client, fake_llm):
    """Простой вопрос root отвечает сам, без субагентов — сценарий только текстом."""
    fake_llm.queue(FakeTurn(text="Короткий ответ."), FakeTurn(text="вопрос"))
    conv = client.post("/api/conversations", json={}).json()
    assert conv["mode"] == "root"

    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "что такое pod"}
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    assert [name for name, _ in events][-1] == "done"
    assert not any(d["name"] == "run_agent" for name, d in events if name == "tool_start")


def test_old_modes_still_available(client, fake_llm):
    """Контракт: прежние режимы создаются и работают, agent:<name> валидируется как раньше."""
    for mode in ("free", "quick", "session", "tuning"):
        created = client.post("/api/conversations", json={"mode": mode, "title": mode})
        assert created.status_code == 200, created.text
        assert created.json()["mode"] == mode

    fake_llm.queue(FakeTurn(text="отвечаю"), FakeTurn(text="заголовок"))
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "привет"}
    ) as resp:
        raw = "".join(resp.iter_text())
    events = parse_sse(raw)
    assert [name for name, _ in events][-1] == "done"
    deltas = "".join(d["text"] for name, d in events if name == "delta")
    assert deltas == "отвечаю "

    # неизвестный режим по-прежнему отклоняется
    assert client.post("/api/conversations", json={"mode": "nope"}).status_code == 422


def test_root_agent_in_catalog_and_registry(container):
    """root зарегистрирован как builtin и виден в инструменте list_agents."""
    spec = container.agent_registry.get("root")
    assert container.agent_registry.is_builtin("root")
    assert {"run_agent", "list_agents", "search"} <= set(spec.tools)

    from app.kernel.tools.spec import ToolContext

    out = container.tools.call("list_agents", {}, ToolContext(channel="mcp"))
    entry = next(a for a in out["agents"] if a["name"] == "root")
    assert entry["builtin"] is True
    assert "run_agent" in entry["tools"]
    catalog = json.dumps(out, ensure_ascii=False)
    assert "repo_scout" in catalog
