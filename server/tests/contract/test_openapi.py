"""Контракт OpenAPI: ключевые пути REST, включая алиасы v1."""


def test_openapi_served(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "learnos"


def test_openapi_has_key_paths(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = [
        "/api/health",
        # база знаний
        "/api/kb/blocks",
        "/api/kb/blocks/{uid}",
        "/api/kb/blocks/{uid}/versions",
        "/api/kb/blocks/{uid}/category",
        "/api/kb/inbox",
        "/api/kb/categories",
        # алиасы v1
        "/api/blocks",
        "/api/blocks/{uid}",
        # обучение
        "/api/courses",
        "/api/sessions",
        "/api/sessions/{ref}/advance",
        "/api/sessions/{ref}/finish",
        # чат (SSE)
        "/api/conversations",
        "/api/conversations/{uid}/messages",
        "/api/conversations/{uid}/stop",
        # библиотека
        "/api/sources",
        "/api/sources/{ref}/chapters/{idx}",
    ]
    for path in expected:
        assert path in paths, f"путь {path} пропал из OpenAPI"


def test_openapi_sse_endpoint_consumes_post(client):
    """SSE-эндпоинт сообщений — POST (GET не должен значиться)."""
    path = client.get("/openapi.json").json()["paths"]["/api/conversations/{uid}/messages"]
    assert "post" in path
    assert "get" not in path
