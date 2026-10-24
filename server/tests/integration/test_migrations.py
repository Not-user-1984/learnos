"""Миграции Alembic: старая БД схемы v1 с данными → head без потерь.

migrations/env.py берёт URL из LEARNOS_DATA_DIR, поэтому БД должна лежать
в <data_dir>/learnos.db, а фронтматтер-блоки — в LEARNOS_KB_DIR.
"""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

SERVER_DIR = Path(__file__).resolve().parent.parent.parent

# схема v1 (до модульного ядра) — как в миграции 0001_baseline
V1_SCHEMA = """
CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    plan_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    local_path TEXT,
    status TEXT NOT NULL DEFAULT 'found',
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    tokens_est INTEGER,
    summary TEXT
);
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    idx INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    state TEXT NOT NULL DEFAULT 'theory',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    transcript_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    session_id INTEGER REFERENCES sessions(id),
    block_uid TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    review_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

V1_BLOCK_MD = "---\nid: blk_test01\ntitle: Тест\ncourse: 1\ntags: [a]\n---\n\n# Тест\n\nТело блока.\n"


@pytest.fixture
def v1_layout(tmp_path, monkeypatch):
    """БД схемы v1 с данными + старый MD-блок в корне kb/."""
    data_dir = tmp_path / "data"
    kb_dir = tmp_path / "kb"
    data_dir.mkdir()
    kb_dir.mkdir()
    monkeypatch.setenv("LEARNOS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LEARNOS_KB_DIR", str(kb_dir))

    db_path = data_dir / "learnos.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(V1_SCHEMA)
    conn.execute(
        "INSERT INTO courses (topic, status, plan_json, created_at) "
        "VALUES ('Kubernetes', 'planned', '{}', '2026-01-01T10:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO sources (course_id, kind, title, url, local_path, status, meta_json) "
        "VALUES (1, 'book', 'K8s Book', NULL, NULL, 'processed', '{}')"
    )
    for idx, title in ((1, "Глава 1"), (2, "Глава 2")):
        conn.execute(
            "INSERT INTO chapters (source_id, idx, title, path, tokens_est, summary) "
            "VALUES (1, ?, ?, ?, 100, '')",
            (idx, title, str(tmp_path / f"ch{idx}.md")),
        )
    conn.execute(
        "INSERT INTO sessions (course_id, idx, status, state, started_at, ended_at, transcript_json) "
        "VALUES (1, 1, 'active', 'debrief', '2026-01-01T10:00:00+00:00', NULL, '[]')"
    )
    conn.execute(
        "INSERT INTO blocks (course_id, session_id, block_uid, title, path, tags_json, sources_json, "
        "review_json, created_at) "
        "VALUES (1, 1, 'blk_test01', 'Тест', 'kb/blk_test01_test.md', '[\"k8s\"]', '[]', '{}', "
        "'2026-01-01T11:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    (kb_dir / "blk_test01_test.md").write_text(V1_BLOCK_MD, encoding="utf-8")
    return data_dir, kb_dir


def _upgrade(data_dir: Path) -> None:
    """Прогнать alembic upgrade head на БД из data_dir."""
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    # абсолютный script_location — не зависит от cwd теста
    cfg.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{data_dir / 'learnos.db'}")
    command.upgrade(cfg, "head")


def test_v1_to_head_moves_data_and_kb(v1_layout):
    data_dir, kb_dir = v1_layout
    _upgrade(data_dir)

    engine = create_engine(f"sqlite:///{data_dir / 'learnos.db'}")
    try:
        with engine.connect() as conn:
            # ревизия дошла до головы
            assert (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0008_chapter_navigation"
            )  # head (обновляется с новыми ревизиями)

            # sources получил uid, строки сохранены
            src = conn.execute(text("SELECT id, uid, kind, title, status FROM sources")).mappings().all()
            assert len(src) == 1
            assert src[0]["uid"].startswith("src_")
            assert src[0]["title"] == "K8s Book"

            # chapters перенесены с сохранением source_id
            chapters = conn.execute(text("SELECT source_id, idx FROM chapters ORDER BY idx")).all()
            assert [(r[0], r[1]) for r in chapters] == [(src[0]["id"], 1), (src[0]["id"], 2)]

            # courses: +uid, topic сохранён и скопирован в title
            crs = conn.execute(text("SELECT uid, title, topic FROM courses")).mappings().all()
            assert crs[0]["uid"].startswith("crs_")
            assert crs[0]["topic"] == "Kubernetes"

            # sessions: +uid, состояние сохранено
            ses = conn.execute(text("SELECT uid, state, transcript_json FROM sessions")).mappings().all()
            assert ses[0]["uid"].startswith("ses_")
            assert ses[0]["state"] == "debrief"

            # blocks: kind=lesson, session_id → session_uid, теги разложены
            blk = (
                conn.execute(text("SELECT block_uid, kind, title, session_uid FROM blocks")).mappings().all()
            )
            assert blk[0]["block_uid"] == "blk_test01"
            assert blk[0]["kind"] == "lesson"
            assert blk[0]["session_uid"] == ses[0]["uid"]
            tags = conn.execute(text("SELECT tag FROM block_tags WHERE block_uid = 'blk_test01'")).all()
            assert [r[0] for r in tags] == ["k8s"]

            # course_id источника v1 переехал в элементы курса
            items = conn.execute(text("SELECT item_type, source_id FROM course_items")).all()
            assert items == [("source", src[0]["id"])]

            # категория и профиль по умолчанию
            assert conn.execute(text("SELECT COUNT(*) FROM categories")).scalar_one() >= 3
            assert (
                conn.execute(text("SELECT value_json FROM settings WHERE key = 'profile'")).scalar_one()
                is not None
            )

        # новые колонки видны инспектору
        insp = inspect(engine)
        assert "uid" in {c["name"] for c in insp.get_columns("sources")}
        assert "kind" in {c["name"] for c in insp.get_columns("blocks")}
    finally:
        engine.dispose()

    # kb: блок переехал в kb/blocks/ с frontmatter v2
    moved = kb_dir / "blocks" / "blk_test01_test.md"
    assert moved.exists()
    assert not (kb_dir / "blk_test01_test.md").exists()
    content = moved.read_text(encoding="utf-8")
    assert "id: blk_test01" in content
    assert "category_status: suggested" in content
    assert "course:" not in content  # ссылка на курс v1 удалена
    assert "kind: lesson" in content

    # categories.yaml появился
    assert (kb_dir / "categories.yaml").exists()


def test_second_upgrade_is_noop(v1_layout):
    data_dir, _kb = v1_layout
    _upgrade(data_dir)
    engine = create_engine(f"sqlite:///{data_dir / 'learnos.db'}")
    with engine.connect() as conn:
        src_uid = conn.execute(text("SELECT uid FROM sources")).scalar_one()
    engine.dispose()

    _upgrade(data_dir)  # повторно — не должно упасть и не менять данные

    engine = create_engine(f"sqlite:///{data_dir / 'learnos.db'}")
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT uid FROM sources")).scalar_one() == src_uid
            assert conn.execute(text("SELECT COUNT(*) FROM blocks")).scalar_one() == 1
    finally:
        engine.dispose()


def test_fresh_empty_db_migrates_to_head(tmp_path, monkeypatch):
    """Пустая БД (новая установка) проходит обе ревизии."""
    data_dir = tmp_path / "data"
    kb_dir = tmp_path / "kb"
    data_dir.mkdir()
    kb_dir.mkdir()
    monkeypatch.setenv("LEARNOS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LEARNOS_KB_DIR", str(kb_dir))

    _upgrade(data_dir)

    engine = create_engine(f"sqlite:///{data_dir / 'learnos.db'}")
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert {"courses", "sources", "chapters", "sessions", "blocks", "categories"} <= tables
    finally:
        engine.dispose()
