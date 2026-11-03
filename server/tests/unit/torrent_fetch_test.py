"""torrent-fetch скилл: провайдеры (Prowlarr/qBit/libgen), режимы suggest/auto и import без сети."""

import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path

import httpx
import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "torrent-fetch"


def _load_run():
    """Загрузить run.py скилла как модуль (провайдеры — через sys.path скилла)."""
    sys.path.insert(0, str(SKILL_DIR))
    spec = importlib.util.spec_from_file_location("torrent_fetch_run", SKILL_DIR / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


run = _load_run()
from providers.libgen import LibgenClient  # noqa: E402
from providers.prowlarr import ProwlarrClient  # noqa: E402
from providers.qbittorrent import QbitClient  # noqa: E402

# ── httpx-моки без сети ─────────────────────────────────────────────

_REAL_CLIENT = httpx.Client


def _client_factory(transport: httpx.MockTransport):
    """Замена httpx.Client: всегда клиент с фиксированным транспортом."""

    def factory(*args, **kwargs):
        kwargs.pop("proxy", None)
        kwargs["transport"] = transport
        return _REAL_CLIENT(**kwargs)

    return factory


def _get_factory(transport: httpx.MockTransport):
    """Замена httpx.get (ProwlarrClient)."""

    def fake_get(url, **kwargs):
        with httpx.Client(transport=transport) as c:
            return c.get(url, **kwargs)

    return fake_get


PROWLARR_ROWS = [
    {
        "title": "Книга с малыми сидами",
        "indexer": "A",
        "size": 100,
        "seeders": 1,
        "leechers": 0,
        "infoHash": "h1",
        "downloadUrl": "http://dl/1",
        "magnetUrl": "magnet:?xt.1",
        "categories": [],
        "publishDate": "2020-01-01T00:00:00Z",
    },
    {
        "title": "Книга популярная",
        "indexer": "B",
        "size": 200,
        "seeders": 42,
        "leechers": 3,
        "infoHash": "h2",
        "downloadUrl": "http://dl/2",
        "magnetUrl": "magnet:?xt.2",
        "categories": [],
        "publishDate": "2024-01-01T00:00:00Z",
    },
    # битая запись: ни сидов, ни magnet — фильтруется
    {"title": "мусор", "indexer": "C", "size": 1, "seeders": 0, "leechers": 0},
]


def test_prowlarr_search_parses_and_sorts(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "k"
        return httpx.Response(200, json=PROWLARR_ROWS)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("providers.prowlarr.httpx.get", _get_factory(transport))
    client = ProwlarrClient("http://prowlarr", "k")
    res = client.search("python", cat="books", limit=10)
    assert [r["title"] for r in res] == ["Книга популярная", "Книга с малыми сидами"]
    assert res[0]["kind"] == "torrent" and res[0]["link"] == "http://dl/2"
    assert res[0]["size"] == 200


def test_qbit_add_ok_and_duplicate(monkeypatch):
    codes = iter([200, 202, 409])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            code = next(codes)
            return httpx.Response(code, text="Ok." if code == 200 else "")
        raise AssertionError(f"неожиданный запрос: {request.url}")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("providers.qbittorrent.httpx.Client", _client_factory(transport))
    qbit = QbitClient("http://qbit", api_key="qbt_x")
    res = qbit.add("magnet:?xt.1", category="learnos-books")
    assert res["added"] and res["category"] == "learnos-books" and not res["duplicate"]
    res2 = qbit.add("magnet:?xt.1", category="learnos-books")
    assert res2["added"] and res2["duplicate"] is True
    # qBit 5.x отвечает 409 на повторное добавление — это тоже дубликат, не ошибка
    res3 = qbit.add("magnet:?xt.1", category="learnos-books")
    assert res3["added"] and res3["duplicate"] is True


def test_qbit_torrents_info(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "name": "t1",
                    "category": "learnos-books",
                    "progress": 1.0,
                    "state": "stalledUP",
                    "size": 5,
                    "hash": "a",
                    "added_on": 2,
                    "content_path": "/downloads/t1.pdf",
                    "save_path": "/downloads",
                },
                {
                    "name": "t0",
                    "category": "",
                    "progress": 0.5,
                    "state": "downloading",
                    "size": 5,
                    "hash": "b",
                    "added_on": 1,
                    "content_path": "/downloads/t0",
                    "save_path": "/downloads",
                },
            ],
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("providers.qbittorrent.httpx.Client", _client_factory(transport))
    qbit = QbitClient("http://qbit", api_key="qbt_x")
    res = qbit.torrents()
    assert res[0]["name"] == "t1" and res[0]["progress"] == 100.0
    assert res[0]["content_path"] == "/downloads/t1.pdf" and res[0]["save_path"] == "/downloads"
    assert res[1]["state"] == "downloading"


def test_libgen_parse_li_rows():
    html = f"""
    <table><tr>
      <td><a href="edition.php?id=1">Fluent Python First edition</a> изд. мусор</td>
      <td>Ramalho, Luciano</td><td>O'Reilly</td><td>2015</td><td>English</td>
      <td>750 pages</td><td>5 MB</td><td>pdf</td>
      <td><a href="/ads.php?md5={"a" * 32}">dl</a></td>
    </tr></table>
    """
    lg = LibgenClient()
    rows = lg._parse_li(html)
    assert rows[0]["md5"] == "a" * 32
    assert rows[0]["title"] == "Fluent Python First edition"
    assert rows[0]["author"] == "Ramalho, Luciano"
    assert rows[0]["ext"] == "pdf"
    assert rows[0]["size"] == 5_000_000


def test_pick_best_torrent_by_seeders():
    cands = [
        {"title": "мало", "seeders": 3, "publish_date": "2024-01-01"},
        {"title": "много", "seeders": 33, "publish_date": "2020-01-01"},
    ]
    assert run._pick_best_torrent(cands)["title"] == "много"


def test_search_suggest_saves_state(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PROWLARR_ROWS)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("providers.prowlarr.httpx.get", _get_factory(transport))
    cfg = {
        "prowlarr": {"url": "http://prowlarr", "api_key": "k"},
        "qbittorrent": {"url": "http://qbit", "api_key": "q"},
        "libgen": {"enabled": False},
        "mode": "suggest",
    }
    state = tmp_path / "last_search.json"
    monkeypatch.setenv("TORRENT_FETCH_STATE", str(state))
    res = run.do_search(cfg, "python", cat="books", auto=False)
    assert res["mode"] == "suggest" and res["count"] == 2
    assert "Книга популярная" in res["table"]
    saved = json.loads(state.read_text())
    assert saved[0]["title"] == "Книга популярная"


def test_add_by_number_uses_learnos_books_category(monkeypatch, tmp_path):
    added = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/torrents/add":
            added["body"] = request.content.decode()
            return httpx.Response(200, text="Ok.")
        raise AssertionError(f"неожиданный запрос: {request.url}")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("providers.qbittorrent.httpx.Client", _client_factory(transport))
    cfg = {"qbittorrent": {"url": "http://qbit", "api_key": "q"}}
    state = tmp_path / "last_search.json"
    cand = {
        "kind": "torrent",
        "title": "Книга",
        "indexer": "B",
        "size": 10,
        "seeders": 5,
        "link": "magnet:?xt.9",
    }
    state.write_text(json.dumps([cand]), encoding="utf-8")
    monkeypatch.setenv("TORRENT_FETCH_STATE", str(state))
    res = run.do_add(cfg, "1", cat="books")
    assert res["added"] and res["kind"] == "torrent"
    assert "learnos-books" in added["body"] and "magnet" in added["body"]


def test_add_bad_index(monkeypatch, tmp_path):
    state = tmp_path / "last_search.json"
    state.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("TORRENT_FETCH_STATE", str(state))
    res = run.do_add({"qbittorrent": {"url": "http://q", "api_key": "x"}}, "7", cat="books")
    assert res["error"] == "bad_index"


def test_main_no_config_returns_error(monkeypatch, tmp_path):
    monkeypatch.setenv("TORRENT_FETCH_CONFIG", str(tmp_path / "nope.json"))
    monkeypatch.setenv("HOME", str(tmp_path))  # цепочка конфига не должна найти реальный ~/.config
    monkeypatch.chdir(tmp_path)
    res = run.main(action="status")
    assert res["error"] == "no_config"


# ── action=auto / import ────────────────────────────────────────────


def test_main_auto_routes_to_search_with_auto(monkeypatch):
    calls = {}
    monkeypatch.setattr(run, "load_config", lambda: {})
    monkeypatch.setattr(
        run,
        "do_search",
        lambda cfg, query, cat="books", auto=False, limit=20: (
            calls.update(query=query, cat=cat, auto=auto) or {"mode": "auto"}
        ),
    )
    assert run.main(action="auto", query="Радченко 1С") == {"mode": "auto"}
    assert calls == {"query": "Радченко 1С", "cat": "books", "auto": True}
    # без query — внятная ошибка, не bad_action
    assert run.main(action="auto")["error"] == "no_query"


_IMPORT_SCHEMA = """
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT, kind TEXT, title TEXT, url TEXT, local_path TEXT,
    status TEXT DEFAULT 'chosen', summary TEXT, meta_json TEXT DEFAULT '{}',
    created_at TEXT, updated_at TEXT
);
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT, target TEXT, status TEXT DEFAULT 'queued',
    progress INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
    message TEXT, error TEXT, created_at TEXT, updated_at TEXT
);
"""


class _FakeQbit:
    def __init__(self, torrents):
        self._torrents = torrents

    def torrents(self, limit=15):
        return self._torrents[:limit]

    def close(self):
        pass


@pytest.fixture
def import_app(monkeypatch, tmp_path):
    """Фейковые app.db/app.paths (как book_splitter_test) + tmp data-каталог."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_IMPORT_SCHEMA)
    conn.commit()

    def _connect():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    fake_db = types.ModuleType("app.db")
    fake_db.get_db = _connect
    fake_paths = types.ModuleType("app.paths")
    data_dir = tmp_path / "data"
    fake_paths.DATA_DIR = data_dir
    monkeypatch.setitem(sys.modules, "app.db", fake_db)
    monkeypatch.setitem(sys.modules, "app.paths", fake_paths)
    yield conn, data_dir
    conn.close()


def _torrent(name, content_path, category="learnos-books", progress=100.0, state="stalledUP"):
    return {
        "name": name,
        "category": category,
        "progress": progress,
        "state": state,
        "size": 10,
        "hash": "d47efb280a61b49c24d6be10c9fee2422a6b500d",
        "content_path": content_path,
        "save_path": "/downloads",
    }


def test_import_copies_pdf_and_creates_source_with_job(monkeypatch, tmp_path, import_app):
    db, data_dir = import_app
    pdf = tmp_path / "Книга тест.pdf"
    pdf.write_bytes(b"%PDF-1.4 test book")
    monkeypatch.setattr(run, "_mk_qbit", lambda cfg: _FakeQbit([_torrent("Книга тест.pdf", str(pdf))]))

    res = run.do_import({"qbittorrent": {}}, "d47efb280a61b49c24d6be10c9fee2422a6b500d")
    assert res["ok"] and res["existed"] is False and res["title"] == "Книга тест"
    uid = res["uid"]
    assert uid.startswith("src_")
    assert (data_dir / "sources" / uid / "original.pdf").read_bytes() == b"%PDF-1.4 test book"

    row = db.execute("SELECT * FROM sources WHERE uid = ?", (uid,)).fetchone()
    assert row["kind"] == "book" and row["status"] == "chosen"
    assert row["title"] == "Книга тест" and row["local_path"].endswith("original.pdf")
    job = db.execute("SELECT * FROM jobs").fetchone()
    assert job["kind"] == "process_source" and job["target"] == uid
    assert job["status"] == "queued" and job["total"] == 1

    # идемпотентность: повтор → тот же uid, existed, без дублей source/job
    res2 = run.do_import({"qbittorrent": {}}, "книга тест")  # матчится по подстроке имени
    assert res2["ok"] and res2["existed"] is True and res2["uid"] == uid
    assert db.execute("SELECT count(*) c FROM sources").fetchone()["c"] == 1
    assert db.execute("SELECT count(*) c FROM jobs").fetchone()["c"] == 1
    db.close()


def test_import_existing_title_with_pdf_suffix_as_hook_writes(monkeypatch, tmp_path, import_app):
    """Hook сохраняет title с «.pdf» — импорт должен распознать такую книгу существующей."""
    db, _data = import_app
    now = "2026-11-03T22:00:00+00:00"
    db.execute(
        "INSERT INTO sources(uid, kind, title, status, created_at, updated_at)"
        " VALUES ('src_hook', 'book', 'Радченко 1С.pdf', 'processed', ?, ?)",
        (now, now),
    )
    db.commit()
    pdf = tmp_path / "Радченко 1С.pdf"
    pdf.write_bytes(b"%PDF-1.4 radchenko")
    monkeypatch.setattr(run, "_mk_qbit", lambda cfg: _FakeQbit([_torrent("Радченко 1С.pdf", str(pdf))]))

    res = run.do_import({"qbittorrent": {}}, "радченко")
    assert res["ok"] and res["existed"] is True and res["uid"] == "src_hook"
    assert db.execute("SELECT count(*) c FROM sources").fetchone()["c"] == 1
    db.close()


def test_import_picks_largest_pdf_from_directory(monkeypatch, tmp_path, import_app):
    db, data_dir = import_app
    files_dir = tmp_path / "раздача"
    files_dir.mkdir()
    (files_dir / "cover.pdf").write_bytes(b"%PDF-" + b"s" * (90 * 1024))  # ниже порога 100 КБ
    (files_dir / "book.pdf").write_bytes(b"%PDF-" + b"b" * (150 * 1024))
    (files_dir / "note.txt").write_text("не pdf")
    monkeypatch.setattr(run, "_mk_qbit", lambda cfg: _FakeQbit([_torrent("раздача", str(files_dir))]))

    res = run.do_import({"qbittorrent": {}}, "раздача")
    assert res["ok"] and res["existed"] is False
    saved = (data_dir / "sources" / res["uid"] / "original.pdf").read_bytes()
    assert saved.startswith(b"%PDF-" + b"b")
    db.close()


def test_import_rejects_unreachable_foreign_and_unfinished(monkeypatch, tmp_path, import_app):
    db, _data = import_app
    pdf = tmp_path / "ok.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    # файл раздачи живёт на хосте qBit и не виден сервису — внятная ошибка, не no_pdf
    monkeypatch.setattr(run, "_mk_qbit", lambda cfg: _FakeQbit([_torrent("r", "/downloads/r.pdf")]))
    res = run.do_import({"qbittorrent": {}}, "r")
    assert res["error"] == "file_unreachable" and "hook" in res["message"]

    # чужая категория — не книга
    monkeypatch.setattr(
        run, "_mk_qbit", lambda cfg: _FakeQbit([_torrent("film", str(pdf), category="movies")])
    )
    assert run.do_import({"qbittorrent": {}}, "film")["error"] == "bad_category"

    # незавершённая раздача
    monkeypatch.setattr(
        run, "_mk_qbit", lambda cfg: _FakeQbit([_torrent("b", str(pdf), progress=40.0, state="downloading")])
    )
    assert run.do_import({"qbittorrent": {}}, "b")["error"] == "not_finished"

    # раздачи с таким именем нет
    monkeypatch.setattr(run, "_mk_qbit", lambda cfg: _FakeQbit([]))
    assert run.do_import({"qbittorrent": {}}, "нет такой")["error"] == "not_found"
    db.close()
