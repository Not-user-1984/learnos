"""GET /api/llm/status и тул llm_status (BB-004/BB-005): детализация под токеном, health чистый."""

from app.kernel.tools.spec import ToolContext


def test_llm_status_endpoint_structure(client):
    r = client.get("/api/llm/status")
    assert r.status_code == 200
    body = r.json()
    assert "configured" in body and "roles" in body and "providers" in body
    # значения ключей не отдаются нигде — только счётчики и номера
    assert "ZAI_API_KEY" not in r.text


def test_llm_status_hidden_from_open_health(client):
    """health открыт без токена — цепочек ключей и params там быть не должно."""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "providers" not in body and "roles" not in body and "keychain" not in body


def test_llm_status_requires_token(token_client):
    assert token_client.get("/api/llm/status").status_code == 401
    r = token_client.get("/api/llm/status", headers={"Authorization": "Bearer secret-token-123"})
    assert r.status_code == 200 and "providers" in r.json()


def test_llm_status_tool_registered_and_visible_to_root(container):
    assert container.tools.has("llm_status")
    root = container.agent_registry.get("root")
    assert "llm_status" in root.tools


def test_llm_status_tool_returns_structure_and_supports_reset(container):
    result = container.tools.call("llm_status", {}, ToolContext(channel="agent"))
    assert "roles" in result and "providers" in result

    reset = container.tools.call("llm_status", {"reset_cooldown": True}, ToolContext(channel="agent"))
    # в тестовом контейнере провайдеры подменены fake'ом — карты cooldown нет, сброс пуст
    assert reset.get("cooldown_reset", {}) == {}
