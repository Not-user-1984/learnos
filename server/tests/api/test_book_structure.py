"""Умная структура книги: куратор глав, outline из БД, картинки глав, mark_chapter_done."""

from __future__ import annotations

import json
from pathlib import Path

# top-записи «после сплиттера»: как у Pro Git — мусор до первой настоящей главы
ENTRIES = [
    {"idx": 1, "title": "Титул", "start_page": 1, "page_count": 1, "snippet": "Pro Git"},
    {"idx": 2, "title": "Оглавление", "start_page": 2, "page_count": 2, "snippet": "Contents"},
    {"idx": 3, "title": "Введение", "start_page": 5, "page_count": 9, "snippet": "О версионном контроле"},
    {"idx": 4, "title": "Глава 2. Основы Git", "start_page": 14, "page_count": 30, "snippet": "Первые шаги"},
    {"idx": 5, "title": "Приложение A. Шпаргалка", "start_page": 400, "page_count": 4, "snippet": "Команды"},
]


def _add_book_source(container, tmp_title: str = "Pro Git", entries: list[dict] | None = None) -> dict:
    """Источник-книга с PDF и главами «после сплиттера» (все top-записи, .md на диске)."""
    from app.modules.library.infra.tables import chapters, sources

    book_entries = entries or ENTRIES
    data_dir = Path(container.settings.data_dir)
    src_dir = data_dir / "sources"
    with container.uow() as uow:
        sid = uow.session.execute(
            sources.insert().values(
                uid="src_test_book",
                kind="book",
                title=tmp_title,
                status="processing",
                meta_json="{}",
                created_at="2026-10-24T00:00:00",
                updated_at="2026-10-24T00:00:00",
            )
        ).inserted_primary_key[0]
        for e in book_entries:
            ch_dir = src_dir / str(sid) / "chapters"
            ch_dir.mkdir(parents=True, exist_ok=True)
            path = ch_dir / f"ch_{e['idx']:02d}.md"
            path.write_text(f"# {e['title']}\n\nтекст главы", encoding="utf-8")
            uow.session.execute(
                chapters.insert().values(
                    source_id=sid,
                    idx=e["idx"],
                    title=e["title"],
                    path=str(path),
                    tokens_est=10,
                    start_page=e["start_page"],
                    end_page=e["start_page"] + e["page_count"] - 1,
                )
            )
    return {"id": sid, "uid": "src_test_book"}


def _chapters(container, source_id: int) -> list[dict]:
    with container.uow() as uow:
        from app.modules.library.infra.tables import chapters

        rows = (
            uow.session.execute(
                chapters.select().where(chapters.c.source_id == source_id).order_by(chapters.c.idx)
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


def test_curate_book_heuristic_drops_front_matter(client, container):
    """Без LLM: титул/оглавление вырезаны, главы перенумерованы, number из названия книги."""
    src = _add_book_source(container)
    result = container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    assert result["curated"] and result["front_matter_dropped"] == 2

    rows = _chapters(container, src["id"])
    assert [(r["idx"], r["title"], r["number"]) for r in rows] == [
        # книга с собственной нумерацией («Глава 2. …») — «Введение» без номера,
        # чтобы не дублировать «Глава 1» с настоящей главой 1
        (1, "Введение", None),
        (2, "Глава 2. Основы Git", 2),  # номер из названия
        (3, "Приложение A. Шпаргалка", None),  # приложение без числа
    ]
    # .md мусорных записей удалён, глав — на месте
    data_dir = Path(container.settings.data_dir)
    assert not (data_dir / "sources" / str(src["id"]) / "chapters" / "ch_01.md").exists()
    assert (data_dir / "sources" / str(src["id"]) / "chapters" / "ch_04.md").exists()

    with container.uow() as uow:
        from app.modules.library.infra.tables import sources

        meta = (
            uow.session.execute(sources.select().where(sources.c.id == src["id"]))
            .mappings()
            .one()["meta_json"]
        )
    assert "Pro Git" in json.loads(meta)["front_matter"]


def test_curate_book_unnumbered_book_gets_positional_numbers(client, container):
    """Книга без номеров в названиях (Pro Git): главы получают позиции 1, 2, …"""
    entries = [
        {"idx": 1, "title": "Оглавление", "start_page": 3, "page_count": 2, "snippet": ""},
        {"idx": 2, "title": "Введение", "start_page": 5, "page_count": 9, "snippet": "о git"},
        {"idx": 3, "title": "Основы Git", "start_page": 14, "page_count": 30, "snippet": ""},
    ]
    src = _add_book_source(container, entries=entries)
    container.library._curate_book(src["id"], src["uid"], {"entries": entries})
    rows = _chapters(container, src["id"])
    assert [(r["idx"], r["title"], r["number"]) for r in rows] == [
        (1, "Введение", 1),
        (2, "Основы Git", 2),
    ]


def test_curate_book_llm_labels_win(client, container, fake_llm):
    """Куратор-LLM: один вызов, классы из ответа модели применяются к всем записям.

    Номера LLM не используются: только из названия книги (позиционные — если
    в книге вообще нет своих номеров).
    """
    from app.llm.providers.fake import FakeTurn

    fake_llm.queue(
        FakeTurn(
            text=json.dumps(
                {
                    "entries": [
                        {"idx": 1, "cls": "front_matter"},
                        {"idx": 2, "cls": "front_matter"},
                        {"idx": 3, "cls": "chapter", "number": 1},
                        {"idx": 4, "cls": "chapter", "number": 2},
                        {"idx": 5, "cls": "appendix"},
                    ]
                }
            )
        )
    )
    src = _add_book_source(container)
    container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    rows = _chapters(container, src["id"])
    # «Введение» — chapter без номера (в книге есть «Глава 2» с собственным номером)
    assert [(r["idx"], r["number"]) for r in rows] == [(1, None), (2, 2), (3, None)]
    # один вызов на книгу
    assert len(fake_llm.requests) == 1


def test_curate_book_llm_incomplete_falls_back_to_heuristic(client, container, fake_llm):
    """LLM вернул не все записи — полный фолбэк на эвристику, job не падает."""
    from app.llm.providers.fake import FakeTurn

    fake_llm.queue(FakeTurn(text=json.dumps({"entries": [{"idx": 1, "cls": "chapter"}]})))
    src = _add_book_source(container)
    result = container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    assert result["curated"]
    rows = _chapters(container, src["id"])
    # как в эвристике: 3 главы, Введение — первая
    assert len(rows) == 3 and rows[0]["title"] == "Введение"


def test_run_process_skips_curator_for_pages_mode(client, container, monkeypatch):
    """pages-режим (PDF без закладок): куратор не вызывается; в toc-режиме — вызывается."""
    src = _add_book_source(container)
    curator_calls = []
    monkeypatch.setattr(
        container.library, "_curate_book", lambda *a, **k: curator_calls.append(1) or {"curated": False}
    )
    monkeypatch.setattr(
        container.library._skills,
        "run",
        lambda name, kw: {"ok": True, "mode": "pages", "chapters": [], "entries": []},
    )
    container.library._run_process({"id": 1, "target": src["uid"]})
    assert curator_calls == []

    monkeypatch.setattr(
        container.library._skills,
        "run",
        lambda name, kw: {"ok": True, "mode": "toc", "chapters": [], "entries": ENTRIES},
    )
    container.library._run_process({"id": 2, "target": src["uid"]})
    assert len(curator_calls) == 1


def test_outline_from_db_with_sections_and_numbers(rest_app, client, container):
    """Новый ингест: страницы/номера/секции глав отдаются из БД (без матча по названиям)."""
    src = _add_book_source(container)
    from app.modules.library.infra.tables import chapters

    with container.uow() as uow:
        uow.session.execute(
            chapters.update()
            .where(chapters.c.source_id == src["id"], chapters.c.idx == 4)
            .values(sections_json=json.dumps([{"title": "Первые шаги", "page": 16}], ensure_ascii=False))
        )
    container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})

    body = client.get(f"/api/sources/{src['uid']}/outline").json()
    assert body["pages"] == {"1": 5, "2": 14, "3": 400}
    assert body["numbers"] == {"2": 2}  # «Введение» в нумерованной книге без номера
    assert body["sections"]["2"] == [{"title": "Первые шаги", "page": 16}]
    assert body["total_pages"] == 403  # max(end_page) без открытия PDF


def test_chapter_images_endpoint(rest_app, client, container):
    """Картинки глав: FileResponse из images/ источника; traversal отсекается."""
    src = _add_book_source(container)
    images_dir = Path(container.settings.data_dir) / "sources" / str(src["id"]) / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "img_p7_0.png").write_bytes(b"\x89PNG-fake")

    r = client.get(f"/api/sources/{src['uid']}/images/img_p7_0.png")
    assert r.status_code == 200 and r.content == b"\x89PNG-fake"
    assert r.headers["content-type"] == "image/png"

    assert client.get(f"/api/sources/{src['uid']}/images/nope.png").status_code == 404
    # path traversal: имя с путём не выходит за images/
    assert client.get(f"/api/sources/{src['uid']}/images/..%2Fchapters%2Fch_01.md").status_code == 404


def test_get_source_returns_chapter_numbers(rest_app, client, container):
    src = _add_book_source(container)
    container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    body = client.get(f"/api/sources/{src['uid']}").json()
    numbers = [(ch["number"], ch["title"]) for ch in body["chapters"]]
    assert numbers == [(None, "Введение"), (2, "Глава 2. Основы Git"), (None, "Приложение A. Шпаргалка")]
