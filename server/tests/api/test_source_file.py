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


def _make_pdf_toc(toc: list[list[int | str]]) -> bytes:
    """Книга из 6 пустых страниц с произвольным деревом закладок."""
    doc = fitz.open()
    for _ in range(6):
        doc.new_page()
    doc.set_toc(toc)  # type: ignore[arg-type]
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
    # названия как из splitter; третья «глава» не совпадает с закладками → страница после предыдущей
    _add_chapters(container, src["id"], ["Глава A", "  глава  b ", "Приложение"])

    r = client.get(f"/api/sources/{src['uid']}/outline")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == src["uid"]
    assert body["total_pages"] == 3
    assert body["pages"] == {"1": 1, "2": 2, "3": 3}

    # повторный вызов — из кэша, результат тот же
    again = client.get(f"/api/sources/{src['uid']}/outline").json()
    assert again["pages"] == body["pages"]


def test_outline_without_toc_falls_back_to_first_page(rest_app, client, container):
    """Книга без закладок: главы есть (взялись иначе), страницы неизвестны — все с 1-й."""
    doc = fitz.open()
    for _ in range(4):
        doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    src = client.post(
        "/api/sources/upload",
        files={"file": ("flat.pdf", buf.getvalue(), "application/pdf")},
        data={"title": "Без закладок"},
    ).json()
    _add_chapters(container, src["id"], ["Раз", "Два"])

    body = client.get(f"/api/sources/{src['uid']}/outline").json()
    assert body["pages"] == {"1": 1, "2": 1}
    assert body["total_pages"] == 4


def test_outline_nested_toc_uses_top_level(rest_app, client, container):
    """Вложенные закладки: главы матчатся по верхнему уровню (как splitter),
    вторые главы-разделы не перебивают страницы."""
    pdf = _make_pdf_toc(
        [
            [1, "Часть I", 1],
            [2, "Введение", 2],
            [1, "Часть II", 4],
            [2, "Раздел", 5],
        ]
    )
    src = client.post(
        "/api/sources/upload",
        files={"file": ("nested.pdf", pdf, "application/pdf")},
        data={"title": "Вложенные закладки"},
    ).json()
    # «Введение» существует только вторым уровнем — не должен матчиться в «Часть II»
    _add_chapters(container, src["id"], ["Часть I", "Часть II", "Эпилог"])

    body = client.get(f"/api/sources/{src['uid']}/outline").json()
    assert body["pages"] == {"1": 1, "2": 4, "3": 5}
    # ветка «level-1 пуст → все уровни» (живые PDF без корневых закладок) в fitz
    # не воспроизводится (set_toc требует первую закладку уровня 1) — покрыта кодом сплиттера


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
