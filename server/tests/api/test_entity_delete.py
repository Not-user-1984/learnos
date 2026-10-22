"""Удаление сущностей (T-022): блоки БЗ, активности, сессии — happy path и 409 при зависимостях."""

from __future__ import annotations

# --- блоки базы знаний ---


def _save_block(container, **kwargs):
    from app.modules.knowledge.domain import BlockDraft

    return container.knowledge.save_block(
        BlockDraft(
            title=kwargs.pop("title", "Блок на удаление"),
            theses=("тезис",),
        ),
        **kwargs,
    )


def test_delete_block_happy_path(rest_app, client, container):
    block = _save_block(container, title="Синхронизация в Python")
    # поиск видит блок до удаления
    found = client.get("/api/search", params={"q": "синхронизация"}).json()
    assert any(b["block_uid"] == block.meta.uid for b in found.get("blocks", []))

    r = client.delete(f"/api/kb/blocks/{block.meta.uid}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == block.meta.uid

    # блок исчез: индекс, версии, файл, поиск
    assert client.get(f"/api/kb/blocks/{block.meta.uid}").status_code == 404
    assert client.get(f"/api/kb/blocks/{block.meta.uid}/versions").status_code == 404
    files = list((container.settings.kb_dir / "blocks").glob(f"{block.meta.path.split('/')[-1]}.md"))
    assert files == []
    found = client.get("/api/search", params={"q": "синхронизация"}).json()
    assert not any(b["block_uid"] == block.meta.uid for b in found.get("blocks", []))
    # повторное удаление — 404
    assert client.delete(f"/api/kb/blocks/{block.meta.uid}").status_code == 404


def test_delete_block_removes_versions(rest_app, client, container):
    block = _save_block(container, title="Блок с версиями")
    container.knowledge.update_block(block.meta.uid, {"summary": "обновлено"}, "правка в тесте")
    assert client.get(f"/api/kb/blocks/{block.meta.uid}/versions").json() != []

    r = client.delete(f"/api/kb/blocks/{block.meta.uid}")
    assert r.status_code == 200, r.text

    with container.uow() as uow:
        from sqlalchemy import text

        n = uow.session.execute(
            text("SELECT count(*) FROM block_versions WHERE block_uid = :u"), {"u": block.meta.uid}
        ).scalar_one()
    assert n == 0


def test_delete_block_referenced_by_course_item_conflict(rest_app, client, container):
    block = _save_block(container, title="Блок в курсе")
    course = client.post("/api/courses", json={"topic": "Курс с блоком"}).json()
    client.post(
        f"/api/courses/{course['uid']}/items",
        json={"item_type": "block", "block_uid": block.meta.uid},
    )

    r = client.delete(f"/api/kb/blocks/{block.meta.uid}")
    assert r.status_code == 409
    assert "курс" in r.json()["message"].lower() or "курс" in r.json()["message"]

    # после удаления элемента курса блок удаляется
    course = client.get(f"/api/courses/{course['uid']}").json()
    item_id = next(i["id"] for i in course["items"] if i["item_type"] == "block")
    assert client.delete(f"/api/courses/{course['uid']}/items/{item_id}").status_code == 200
    assert client.delete(f"/api/kb/blocks/{block.meta.uid}").status_code == 200


# --- активности ---


def test_delete_activity_happy_path(rest_app, client):
    """Активность без сессий удаляется; разговор остаётся (отвязан)."""
    src = client.post("/api/sources", json={"kind": "web", "title": "Статья"}).json()
    act = client.post("/api/activities", json={"source": src["uid"]}).json()
    conv = client.post(
        "/api/conversations",
        json={"mode": "quick", "activity": act["uid"], "chapter": 1, "title": "Разбор"},
    ).json()

    r = client.delete(f"/api/activities/{act['uid']}")
    assert r.status_code == 200, r.text
    assert client.get(f"/api/activities/{act['uid']}").status_code == 404
    # разговор жив, активность из списка ушла
    assert client.get(f"/api/conversations/{conv['uid']}").status_code == 200
    assert all(a["uid"] != act["uid"] for a in client.get("/api/activities").json())
    # повторное удаление — 404
    assert client.delete(f"/api/activities/{act['uid']}").status_code == 404


def test_delete_activity_with_sessions_conflict(rest_app, client):
    src = client.post("/api/sources", json={"kind": "web", "title": "Статья с сессией"}).json()
    act = client.post("/api/activities", json={"source": src["uid"]}).json()
    client.post("/api/sessions", json={"activity": act["uid"]})

    r = client.delete(f"/api/activities/{act['uid']}")
    assert r.status_code == 409
    assert "сесси" in r.json()["message"]
    assert client.get(f"/api/activities/{act['uid']}").status_code == 200


# --- сессии ---


def test_delete_session_happy_path(rest_app, client):
    course = client.post("/api/courses", json={"topic": "Курс"}).json()
    s = client.post("/api/sessions", json={"course_id": course["id"]}).json()

    r = client.delete(f"/api/sessions/{s['session_uid']}")
    assert r.status_code == 200, r.text
    assert client.get(f"/api/sessions/{s['session_uid']}").status_code == 404
    assert client.delete(f"/api/sessions/{s['session_uid']}").status_code == 404


def test_delete_session_with_block_conflict(rest_app, client, container):
    """По сессии создан блок БЗ — удаление запрещено (ядро продукта: блок хранит сессию-источник)."""
    course = client.post("/api/courses", json={"topic": "Курс с блоком"}).json()
    s = client.post("/api/sessions", json={"course_id": course["id"]}).json()
    _save_block(container, title="Блок по сессии", session_uid=s["session_uid"])

    r = client.delete(f"/api/sessions/{s['session_uid']}")
    assert r.status_code == 409
    assert "блок" in r.json()["message"]
    assert client.get(f"/api/sessions/{s['session_uid']}").status_code == 200

    # блок удалён — сессия удаляется
    block_uid = container.knowledge.list_blocks()[0].uid
    assert client.delete(f"/api/kb/blocks/{block_uid}").status_code == 200
    assert client.delete(f"/api/sessions/{s['session_uid']}").status_code == 200
