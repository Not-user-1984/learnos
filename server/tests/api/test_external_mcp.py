"""Внешние MCP-подключения: конструктор, валидации, безопасный probe, обёртки."""

import json

from app.llm.providers.fake import FakeTurn


def _bad_port_url() -> str:
    # гарантированно закрытый порт на localhost: соединение откажёт быстро
    return "http://127.0.0.1:9/mcp"


def test_probe_unreachable_is_safe(client):
    """Недоступный сервер не роняет запрос — возвращает понятную ошибку."""
    r = client.post("/api/mcpext/probe", json={"url": _bad_port_url()})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["error"]


def test_probe_validates_url(client):
    body = client.post("/api/mcpext/probe", json={"url": "not-a-url"}).json()
    assert body["ok"] is False and "http" in body["error"]


def test_draft_parses_link_and_config(client, fake_llm):
    """LLM-конструктор: ссылка → конфиг; имя нормализуется."""
    fake_llm.queue(
        FakeTurn(
            text=json.dumps(
                {
                    "name": "GitHub",
                    "url": "https://mcp.github.com/mcp",
                    "description": "Инструменты GitHub.",
                    "headers": {},
                    "summary": "Подключаем GitHub MCP.",
                }
            )
        )
    )
    d = client.post("/api/mcpext/draft", json={"brief": "вот ссылка https://mcp.github.com/mcp"}).json()
    assert d["name"] == "github"  # нормализован в slug
    assert d["url"] == "https://mcp.github.com/mcp"


def test_create_validates_name_url_and_unique(client):
    base = {"url": "https://example.com/mcp", "description": "тест", "headers": {}}
    # кривое имя
    assert client.post("/api/mcpext", json={**base, "name": "Плохо"}).status_code in (400, 422)
    # не http
    assert client.post(
        "/api/mcpext", json={"name": "good", "url": "ftp://x", "description": "", "headers": {}}
    ).status_code in (400, 422)
    # create уходит в probe живьём — сервер недоступен, но подключение создаётся со статусом error
    r = client.post("/api/mcpext", json={**base, "name": "good", "url": _bad_port_url()})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["connected"] is False and body["mcp"] == "good"
    listing = client.get("/api/mcpext").json()
    assert listing[0]["status"] == "error" and listing[0]["tools_count"] == 0
    # дубль имени — конфликт
    assert client.post("/api/mcpext", json={**base, "name": "good", "url": _bad_port_url()}).status_code in (
        400,
        409,
    )
    # удаление
    assert client.delete("/api/mcpext/good").status_code == 200


def test_unreachable_mcp_does_not_break_startup(container):
    """load_on_start с недоступным сервером (кэш инструментов пуст) — просто без обёрток."""
    loaded = container.mcpext.load_on_start()
    assert isinstance(loaded, int)


def test_wrapper_registration_flow(container):
    """Обёртки: register по кэшу инструментов, unregister при удалении."""
    svc = container.mcpext
    tools = [
        {"name": "search-issues", "description": "поиск задач", "input_schema": {"type": "object"}},
        {"name": "get_pr", "description": "получить PR", "input_schema": {"type": "object"}},
    ]
    svc._register_wrappers("gh", "https://example.com/mcp", {}, tools)  # noqa: SLF001 — тест сервиса
    reg = container.tools
    assert reg.has("mcp_gh_search_issues") and reg.has("mcp_gh_get_pr")
    # вызов обёртки недоступного сервера — аккуратная ошибка агенту
    out = reg.call("mcp_gh_get_pr", {"n": 1}, type("C", (), {"channel": "agent"})())
    assert "error" in out and out["error"] == "remote_unavailable"
    svc._unregister_wrappers("gh")  # noqa: SLF001
    assert not reg.has("mcp_gh_search_issues")
