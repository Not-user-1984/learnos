"""Сплиттер книг: главы из закладок с картинками, страницами и секциями (тестовый PDF)."""

import importlib.util
import sqlite3
import sys
import types
from pathlib import Path

import fitz
import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "book-splitter"

# крошечный PNG 8x8 для insert_image
_PNG = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8)).tobytes("png")

SCHEMA = """
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT, kind TEXT, title TEXT, url TEXT, local_path TEXT,
    status TEXT DEFAULT 'chosen', summary TEXT, meta_json TEXT DEFAULT '{}'
);
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    idx INTEGER NOT NULL, title TEXT NOT NULL, path TEXT NOT NULL,
    tokens_est INTEGER, summary TEXT,
    key_points_json TEXT DEFAULT '[]', has_exercises INTEGER DEFAULT 0,
    number INTEGER, start_page INTEGER, end_page INTEGER,
    sections_json TEXT DEFAULT '[]'
);
"""


@pytest.fixture
def splitter(tmp_path):
    """run.py сплиттера с фейковыми app.db/app.paths на tmp-каталоге."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    fake_db = types.ModuleType("app.db")

    def _connect():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    fake_db.get_db = _connect
    fake_paths = types.ModuleType("app.paths")
    fake_paths.DATA_DIR = data_dir
    saved = {m: sys.modules.get(m) for m in ("app.db", "app.paths")}
    sys.modules["app.db"], sys.modules["app.paths"] = fake_db, fake_paths
    try:
        spec = importlib.util.spec_from_file_location("book_splitter_run_test", SKILL_DIR / "run.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        yield mod, _connect(), data_dir
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _make_book(path: Path) -> None:
    """Книжка: титул (картинка+текст), оглавление, Введение (3 стр.),
    Глава 2 (4 стр., картинка-схема + декоративная мелкая), Приложение A."""
    doc = fitz.open()
    for _ in range(10):
        doc.new_page()

    def text(page_no: int, s: str) -> None:
        doc[page_no].insert_text((72, 72), s)

    # титул: текст + большая «обложка»
    text(0, "Pro Git")
    doc[0].insert_image(fitz.Rect(50, 100, 300, 200), stream=_PNG)
    text(1, "Contents")
    for i in range(2, 5):
        text(i, f"Введение, часть {i - 1}. Текст введения книги Pro Git здесь.")
    # глава 2: страницы 6–9, схема на 7-й и декоративная мелочь на 8-й
    text(5, "Глава 2. Основы Git")
    doc[5].insert_image(fitz.Rect(80, 120, 400, 300), stream=_PNG)  # на первой странице главы
    text(6, "Схема областей Git ниже.")
    doc[6].insert_image(fitz.Rect(80, 150, 350, 330), stream=_PNG)  # большая схема
    doc[7].insert_image(fitz.Rect(80, 150, 120, 170), stream=_PNG)  # декоративная < 40pt
    text(7, "Хвост главы.")
    text(8, "Приложение A. Шпаргалка команд Git.")
    doc.set_toc(
        [
            [1, "Титул", 1],
            [1, "Оглавление", 2],
            [1, "Введение", 3],
            [1, "Глава 2. Основы Git", 6],
            [2, "Первые шаги", 7],
            [2, "Запись изменений", 8],
            [1, "Приложение A. Шпаргалка", 10],
        ]
    )
    doc.save(path)
    doc.close()


def test_splitter_parts_book_takes_level2_as_chapters(splitter, tmp_path):
    """Книга с частями (Любанович): level-1 — «Часть I/II», главы в level-2.

    Главами становятся level-2 внутри частей (+ не-частные level-1 для куратора),
    секциями — level-3; сами части главами не делаются.
    """
    mod, db, data_dir = splitter
    doc = fitz.open()
    for _ in range(12):
        doc.new_page()
    for i in range(12):
        doc[i].insert_text((72, 72), f"страница {i + 1}")
    doc.set_toc(
        [
            [1, "Предисловие", 2],
            [2, "Для кого эта книга", 2],
            [1, "Часть I. Замок", 3],
            [2, "Глава 1. Введение", 3],
            [3, "Тайны", 4],
            [2, "Глава 2. Типы", 5],
            [1, "Часть II. Инструменты", 8],
            [2, "Глава 3. Данные", 8],
            [3, "Тексты", 9],
        ]
    )
    pdf = tmp_path / "parts.pdf"
    doc.save(pdf)
    doc.close()
    db.execute(
        "INSERT INTO sources(uid, kind, title, local_path) VALUES ('src_parts', 'book', ?, ?)",
        ("Простой Python", str(pdf)),
    )
    db.commit()

    result = mod.main(source_id=1)
    assert result["ok"], result
    titles = [e["title"] for e in result["entries"]]
    # части исчезли; level-2 вне частей (из предисловия) тоже не главы —
    # их текст остаётся в диапазоне не-частной level-1 записи для куратора
    assert titles == [
        "Предисловие",
        "Глава 1. Введение",
        "Глава 2. Типы",
        "Глава 3. Данные",
    ]

    rows = {
        r["title"]: r
        for r in db.execute(
            "SELECT title, start_page, end_page, sections_json FROM chapters ORDER BY idx"
        ).fetchall()
    }
    db.close()
    assert (rows["Глава 1. Введение"]["start_page"], rows["Глава 1. Введение"]["end_page"]) == (3, 4)
    assert "Тайны" in rows["Глава 1. Введение"]["sections_json"]
    assert "Тексты" in rows["Глава 3. Данные"]["sections_json"]
    # части не стали главами
    assert "Часть I. Замок" not in rows and "Часть II. Инструменты" not in rows


def test_splitter_chapters_pages_sections_and_images(splitter, tmp_path):
    mod, db, data_dir = splitter
    pdf = tmp_path / "book.pdf"
    _make_book(pdf)
    db.execute(
        "INSERT INTO sources(uid, kind, title, local_path) VALUES ('src_test', 'book', ?, ?)",
        ("Pro Git", str(pdf)),
    )
    db.commit()

    result = mod.main(source_id=1)
    assert result["ok"], result
    # все top-записи как есть — классификацию делает куратор в сервисе
    assert [e["title"] for e in result["entries"]] == [
        "Титул",
        "Оглавление",
        "Введение",
        "Глава 2. Основы Git",
        "Приложение A. Шпаргалка",
    ]

    rows = db.execute(
        "SELECT idx, title, start_page, end_page, sections_json FROM chapters ORDER BY idx"
    ).fetchall()
    db.close()
    by_title = {r["title"]: r for r in rows}
    ch2 = by_title["Глава 2. Основы Git"]
    assert (ch2["start_page"], ch2["end_page"]) == (6, 9)
    assert "Первые шаги" in ch2["sections_json"]

    # картинки: обложка титула, схема главы — большие (сохранены); декоративная — нет
    md = (data_dir / "sources" / "1" / "chapters" / "ch_04.md").read_text(encoding="utf-8")
    assert "![рисунок](/api/sources/src_test/images/img_p7_0.png)" in md
    images = sorted(p.name for p in (data_dir / "sources" / "1" / "images").glob("*.png"))
    assert "img_p7_0.png" in images
    assert not any(n.startswith("img_p8") for n in images), "декоративная мелкая картинка не рендерится"
    assert (data_dir / "sources" / "1" / "images" / "img_p7_0.png").stat().st_size > 0


def test_splitter_reprocess_cleans_old_output(splitter, tmp_path):
    """Переобработка затирает старые .md глав и картинки (не оставляет призраков)."""
    mod, db, data_dir = splitter
    pdf = tmp_path / "book.pdf"
    _make_book(pdf)
    db.execute(
        "INSERT INTO sources(uid, kind, title, local_path) VALUES ('src_test', 'book', ?, ?)",
        ("Pro Git", str(pdf)),
    )
    db.commit()
    assert mod.main(source_id=1)["ok"]
    ghosts = data_dir / "sources" / "1" / "chapters" / "ghost.md"
    ghosts.write_text("старье", encoding="utf-8")
    stale_img = data_dir / "sources" / "1" / "images" / "img_p99_0.png"
    stale_img.write_bytes(b"old")

    assert mod.main(source_id=1)["ok"]
    db.close()
    chapters_dir = data_dir / "sources" / "1" / "chapters"
    assert not ghosts.exists()
    assert not stale_img.exists()
    assert len(list(chapters_dir.glob("ch_*.md"))) == 5
