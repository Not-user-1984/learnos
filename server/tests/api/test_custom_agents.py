"""Кастомные агенты: конструктор (LLM-драфт), CRUD, режим чата agent:<name>, удаление."""

import json

from app.llm.providers.fake import FakeTurn


def test_custom_agent_full_cycle(client, fake_llm, container):
    # конструктор: LLM собирает драфт по пожеланию
    designer_out = {
        "name": "homelab_helper",
        "description": "Помощник по хомлабу: подсказывает команды и следит за сервисами.",
        "prompt": (
            "Ты — помощник по домашнему серверу Дмитрия.\n\n"
            "1. Отвечай коротко.\n2. Команды — в блоках кода.\n\n"
            "Отвечай по-русски, Markdown-ом."
        ),
        "tools": ["search", "list_sources"],
        "summary": "Агент по хомлабу с поиском по базе.",
    }
    fake_llm.queue(FakeTurn(text=json.dumps(designer_out, ensure_ascii=False)))
    draft = client.post("/api/tuning/agents/draft", json={"brief": "агент по хомлабу"}).json()
    assert draft["name"] == "homelab_helper"
    assert "search" in draft["tools"]
    assert draft["available_tools"], "в драфте должен быть каталог инструментов"

    # создание: агент появляется в реестре и в списке промптов
    created = client.post(
        "/api/tuning/agents",
        json={
            "name": draft["name"],
            "description": draft["description"],
            "prompt": draft["prompt"],
            "tools": draft["tools"],
        },
    )
    assert created.status_code == 200, created.text
    agents = client.get("/api/tuning/agents").json()
    assert [a["name"] for a in agents] == ["homelab_helper"]

    info = client.get("/api/tuning/prompts/homelab_helper").json()
    assert info["custom"] is True
    assert "list_sources" in info["tools"]
    assert "домашнему серверу" in info["content"]

    # режим чата agent:<name>: разговор работает
    conv = client.post(
        "/api/conversations",
        json={"mode": "agent:homelab_helper", "title": "тест кастомного"},
    )
    assert conv.status_code == 200, conv.text
    uid = conv.json()["uid"]
    fake_llm.queue(FakeTurn(text="Вот команда: uptime"))
    with client.stream("POST", f"/api/conversations/{uid}/messages", json={"content": "привет"}) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    assert "команда" in raw and "uptime" in raw and "event: done" in raw

    # удаление кастомного — можно, встроенного — нельзя
    assert client.delete("/api/tuning/agents/homelab_helper").status_code == 200
    assert client.delete("/api/tuning/agents/free_chat").status_code in (400, 409)
    assert client.get("/api/tuning/prompts/homelab_helper").status_code == 404

    # после удаления режим недоступен для новых разговоров
    assert client.post("/api/conversations", json={"mode": "agent:homelab_helper"}).status_code in (400, 422)


def test_create_custom_agent_validates(client):
    # имя занято встроенным
    r = client.post(
        "/api/tuning/agents",
        json={"name": "free_chat", "description": "клон", "prompt": "x" * 50, "tools": []},
    )
    assert r.status_code in (400, 409)
    # кривое имя
    r = client.post(
        "/api/tuning/agents",
        json={"name": "Плохоё Имя", "description": "d", "prompt": "x" * 50, "tools": []},
    )
    assert r.status_code in (400, 422)
    # неизвестный инструмент
    r = client.post(
        "/api/tuning/agents",
        json={"name": "good_name", "description": "d", "prompt": "x" * 50, "tools": ["no_such_tool"]},
    )
    assert r.status_code in (400, 422)


def test_custom_agents_survive_container_rebuild(client, fake_llm, container):
    """Кастомный агент живёт в БД: перезагрузка реестра поднимает его заново."""
    client.post(
        "/api/tuning/agents",
        json={
            "name": "persister",
            "description": "Живёт в БД",
            "prompt": "Ты — тестовый агент. Отвечай одной строкой.\n\nПо-русски.",
            "tools": [],
        },
    )
    loaded = container.tuning.load_custom_agents()
    assert loaded >= 1
    assert any(a["name"] == "persister" for a in container.tuning.custom_agents())
    client.delete("/api/tuning/agents/persister")
