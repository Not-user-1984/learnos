"""PDF-оригинал источника: раздача файла и матчинг глав с закладками (outline)."""

from __future__ import annotations

import io

import fitz


def _make_pdf() -> bytes:
    """Маленькая книга: 3 страницы, закладки верхнего уровня «Глава A/B/C»."""
    doc = fitz.open()
    for i, name in enumerate(("Глава A", "Глава B", "Глава C"), start=1):
        page = doc.new_page()
        page.insert_text((72, 96), f"{name} — страница {i}")
    doc.set_toc([[1, "Глава A", 1], [1, "Глава B", 2], [1, "Глава C", 3]])
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _add_chapters(container, source_id: int, titles: list[str]) -> None:
    """Главы напрямую в БД — как их создал бы book-splitter из того же TOC."""
    from app.modules.library.infra.tables import chapters

    with container.uow() as uow:
        for idx, title in enumerate(titles, start=1):
            uow.session.execute(
                chapters.insert().values(
                    source_id=source_id, idx=idx, title=title, path=f"/tmp/ch_{idx}.md", tokens_est=1
                )
            )


def test_source_file_served_inline(rest_app, client):
    src = client.post(
        "/api/sources/upload",
        files={"file": ("book.pdf", _make_pdf(), "application/pdf")},
        data={"title": "Тестовая книга"},
    ).json()
    r = client.get(f"/api/sources/{src['uid']}/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert "inline" in r.headers.get("content-disposition", "")


def test_outline_matches_chapters_to_toc_pages(rest_app, client, container):
    src = client.post(
        "/api/sources/upload",
        files={"file": ("book.pdf", _make_pdf(), "application/pdf")},
        data={"title": "Книга с закладками"},
    ).json()
    # названия как из splitter; третья «глава» не совпадает с закладками → страница предыдущей
    _add_chapters(container, src["id"], ["Глава A", "  глава  b ", "Приложение"])

    r = client.get(f"/api/sources/{src['uid']}/outline")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == src["uid"]
    assert body["total_pages"] == 3
    assert body["pages"] == {"1": 1, "2": 2, "3": 2}

    # повторный вызов — из кэша, результат тот же
    again = client.get(f"/api/sources/{src['uid']}/outline").json()
    assert again["pages"] == body["pages"]


def test_source_file_not_found_cases(rest_app, client):
    # не-книга (web без файла)
    web = client.post("/api/sources", json={"kind": "web", "title": "Статья"}).json()
    assert client.get(f"/api/sources/{web['uid']}/file").status_code == 404
    assert client.get(f"/api/sources/{web['uid']}/outline").status_code == 404
    # book без файла на диске
    book = client.post("/api/sources", json={"kind": "book", "title": "Без файла"}).json()
    assert client.get(f"/api/sources/{book['uid']}/file").status_code == 404
    # несуществующий источник
    assert client.get("/api/sources/src_nope/file").status_code == 404
