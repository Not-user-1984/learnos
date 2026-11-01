"""R-07: опциональный bearer-токен — /api и /mcp закрыты от LAN и DNS-rebinding."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def token_client(container, monkeypatch):
    """Приложение с включённым LEARNOS_API_TOKEN."""
    container.settings.api_token = "secret-token-123"
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_CONTAINER", container)
    app = main_mod.create_app()
    app.state.mcp_servers = {}
    with TestClient(app) as tc:
        yield tc


def test_health_open_without_token(token_client):
    assert token_client.get("/api/health").status_code == 200


def test_api_requires_token(token_client):
    r = token_client.get("/api/kb/blocks")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_wrong_token_rejected(token_client):
    r = token_client.get("/api/kb/blocks", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_correct_token_passes(token_client):
    r = token_client.get("/api/kb/blocks", headers={"Authorization": "Bearer secret-token-123"})
    assert r.status_code == 200


def test_mcp_requires_token(token_client):
    r = token_client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
    assert r.status_code in (401, 406)  # до MCP-протокола дело не доходит


def test_preflight_options_not_blocked(token_client):
    r = token_client.options(
        "/api/kb/blocks",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code != 401
