"""REST API: health, полный учебный цикл до блока в KB, маппинг ошибок."""

DRAFT = {
    "title": "Сетевая модель подов",
    "summary": "CNI и pause-контейнер",
    "kind": "lesson",
    "concepts": [{"term": "Pod", "definition": "минимальный юнит"}],
    "theses": ["у каждого пода свой netns"],
    "weak_spots": ["veth-пары"],
    "tags": ["k8s"],
    "category_suggestion": "infra/kubernetes",
}


def test_health_without_llm_key(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # llm.yaml в тестах отсутствует → LLM не настроен
    assert body["llm_configured"] is False
    assert body["llm_keys"] == 0
    assert body["tools"] > 0
    assert body["worker_running"] is True


def test_full_learning_cycle_creates_block(client, container):
    # 1. курс
    course = client.post("/api/courses", json={"topic": "Kubernetes"}).json()
    assert course["uid"].startswith("crs_")
    assert course["topic"] == "Kubernetes"

    # 2. источник
    src = client.post("/api/sources", json={"kind": "book", "title": "K8s Book"}).json()
    assert src["uid"].startswith("src_")
    assert src["kind"] == "book"
    assert src["status"] == "chosen"

    # 3. активность по источнику
    act = client.post("/api/activities", json={"source": src["uid"]}).json()
    assert act["uid"].startswith("act_")
    assert act["cursor_chapter"] == 1
    assert client.get(f"/api/activities/{act['uid']}").json()["total_chapters"] == 0

    # 4. сессия из активности
    ses = client.post("/api/sessions", json={"activity": act["uid"]}).json()
    assert ses["state"] == "theory"
    assert ses["status"] == "active"
    assert "theory_done" in ses["allowed_events"]
    ref = ses["session_uid"]

    # 5. переходы стейт-машины
    states = [
        client.post(f"/api/sessions/{ref}/advance", json={"event": "theory_done"}).json()["state"],
        client.post(f"/api/sessions/{ref}/advance", json={"event": "go_practice"}).json()["state"],
        client.post(f"/api/sessions/{ref}/advance", json={"event": "practice_done"}).json()["state"],
    ]
    assert states == ["check", "practice", "debrief"]

    # 6. финиш с драфтом блока (тело запроса = сам драфт)
    draft = {**DRAFT, "sources": [{"source": src["uid"], "chapter": 1, "title": "K8s Book"}]}
    fin = client.post(f"/api/sessions/{ref}/finish", json=draft).json()
    uid = fin["block_uid"]
    assert uid.startswith("blk_")
    assert fin["ok"] is True
    assert fin["_card"]["type"] == "block_saved"
    assert fin["_card"]["title"] == "Сетевая модель подов"

    # сессия закрыта
    closed = client.get(f"/api/sessions/{ref}").json()
    assert closed["status"] == "finished"
    assert closed["state"] == "done"

    # 7. блок в базе знаний
    blocks = client.get("/api/kb/blocks").json()
    assert [b["block_uid"] for b in blocks] == [uid]
    detail = client.get(f"/api/kb/blocks/{uid}").json()
    assert "# Сетевая модель подов" in detail["content"]
    assert detail["category_path"] == "infra/kubernetes"
    assert detail["tags"] == ["k8s"]
    assert detail["sources"][0]["source"] == src["uid"]

    # 8. категория подтверждается автоматически (categorizer при создании) — inbox пуст
    assert detail["category_status"] == "confirmed"
    assert client.get("/api/kb/inbox").json() == []

    # 9. категорию можно сменить вручную — блок переезжает
    r = client.post(f"/api/kb/blocks/{uid}/category", json={"path": "infra/networking", "confirm": True})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert client.get(f"/api/kb/blocks/{uid}").json()["category_path"] == "infra/networking"

    # 10. версии: сервисная правка (update_block — MCP-инструмент) сохраняет v1
    updated = container.knowledge.update_block(
        uid, {"append_theses": ["дозакрепить netns"]}, reason="тест правки"
    )
    assert updated.meta.version == 2
    versions = client.get(f"/api/kb/blocks/{uid}/versions").json()
    assert [v["version"] for v in versions] == [1]
    assert versions[0]["reason"] == "тест правки"
    assert client.get(f"/api/kb/blocks/{uid}").json()["version"] == 2

    # файл блока на диске содержит обе версии контента
    content = container.settings.kb_dir / "blocks" / f"{updated.meta.path}.md"
    assert "дозакрепить netns" in content.read_text(encoding="utf-8")


def test_error_mapping(client):
    # 404: несуществующий блок — тело ошибки в формате {"error", "message"}
    r = client.get("/api/kb/blocks/blk_missing00")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"
    assert "message" in r.json()

    # 404: несуществующая сессия
    assert client.get("/api/sessions/99999").status_code == 404

    # невалидный переход advance → InvalidState (HTTP 409, код invalid_event)
    course = client.post("/api/courses", json={"topic": "тема"}).json()
    ses = client.post("/api/sessions", json={"course_id": course["id"]}).json()
    r = client.post(f"/api/sessions/{ses['session_uid']}/advance", json={"event": "go_practice"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "invalid_event"
    assert "недопустимо" in body["message"]

    # finish вне debrief → 409 invalid_state
    r = client.post(f"/api/sessions/{ses['session_uid']}/finish", json=dict(DRAFT))
    assert r.status_code == 409
    assert r.json()["error"] == "invalid_state"

    # невалидный kind источника → 422 validation_failed
    r = client.post("/api/sources", json={"kind": "кирпич", "title": "x"})
    assert r.status_code == 422
    assert r.json()["error"] == "validation_failed"


def test_v1_alias_routes(client):
    assert client.get("/api/blocks").status_code == 200
    assert client.get("/api/blocks").json() == []
    assert client.get("/api/blocks/blk_missing00").status_code == 404


def test_conversations_crud(client):
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    assert conv["uid"].startswith("cnv_")
    assert conv["mode"] == "free"
    assert conv["title"] == "Новый разговор"

    listed = client.get("/api/conversations", params={"mode": "free"}).json()
    assert [c["uid"] for c in listed] == [conv["uid"]]

    renamed = client.patch(f"/api/conversations/{conv['uid']}", json={"title": "Мой разговор"}).json()
    assert renamed["title"] == "Мой разговор"

    assert client.delete(f"/api/conversations/{conv['uid']}").json()["ok"] is True
    assert client.get(f"/api/conversations/{conv['uid']}").status_code == 404


def test_research_providers_endpoint(client):
    """GET /api/research/providers — «где агент ищет» для блока UI настроек."""
    r = client.get("/api/research/providers")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"web", "academic", "video"}
    for cat in body.values():
        assert cat["providers"], f"пустая категория {cat}"
        assert all({"name", "enabled", "note"} <= set(p) for p in cat["providers"])
    academic_names = [p["name"] for p in body["academic"]["providers"]]
    assert academic_names == ["arxiv", "openalex", "semantic_scholar"]
