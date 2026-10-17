"""Удаление источника: чистый случай, с курсом, и запрет при блоках (регрессия FK)."""

from __future__ import annotations


def test_delete_source_happy_path(rest_app, client):
    src = client.post("/api/sources", json={"kind": "web", "title": "Времянка"}).json()
    r = client.delete(f"/api/sources/{src['uid']}")
    assert r.status_code == 200
    assert client.get(f"/api/sources/{src['uid']}").status_code == 404


def test_delete_source_referenced_by_course_item(rest_app, client):
    """Источник в элементах курса: удаляем элемент, затем источник — без FK-ошибок."""
    course = client.post("/api/courses", json={"topic": "Курс удаления"}).json()
    src = client.post("/api/sources", json={"kind": "web", "title": "Источник в курсе"}).json()
    course = client.post(
        f"/api/courses/{course['uid']}/items",
        json={"item_type": "source", "source": src["uid"], "note": "проверка"},
    ).json()
    item_id = next(i["id"] for i in course["items"] if i["item_type"] == "source")

    r_item = client.delete(f"/api/courses/{course['uid']}/items/{item_id}")
    assert r_item.status_code == 200, r_item.text
    r_src = client.delete(f"/api/sources/{src['uid']}")
    assert r_src.status_code == 200, r_src.text
    assert client.get(f"/api/sources/{src['uid']}").status_code == 404


def test_delete_source_with_blocks_conflict(rest_app, client, container):
    from app.modules.knowledge.domain import BlockDraft, BlockSource

    src = client.post("/api/sources", json={"kind": "web", "title": "С блоком"}).json()
    container.knowledge.save_block(
        BlockDraft(
            title="Блок на источник",
            theses=("тезис",),
            sources=(BlockSource(source=src["uid"]),),
        )
    )
    r = client.delete(f"/api/sources/{src['uid']}")
    assert r.status_code == 409
    assert "блоки" in r.json()["message"]


def test_delete_source_with_activity_and_conversation(rest_app, client):
    """Источник с активностью и разговором: источник и активности уходят, история чата остаётся."""
    src = client.post("/api/sources", json={"kind": "book", "title": "Книга с разбором"}).json()
    act = client.post("/api/activities", json={"source": src["uid"]}).json()
    conv = client.post(
        "/api/conversations",
        json={"mode": "quick", "activity": act["uid"], "chapter": 1, "title": "Разбор книги"},
    ).json()

    r = client.delete(f"/api/sources/{src['uid']}")
    assert r.status_code == 200, r.text

    # источник исчез
    assert client.get(f"/api/sources/{src['uid']}").status_code == 404
    # разговор остался (отвязан от активности) и открывается
    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    assert fresh["uid"] == conv["uid"]
