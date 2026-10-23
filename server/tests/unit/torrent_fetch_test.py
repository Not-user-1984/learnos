"""torrent-fetch скилл: провайдеры (Prowlarr/qBit/libgen) и режимы suggest/auto без сети."""

import importlib.util
import json
import sys
from pathlib import Path

import httpx

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
    codes = iter([200, 202])

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
                },
                {
                    "name": "t0",
                    "category": "",
                    "progress": 0.5,
                    "state": "downloading",
                    "size": 5,
                    "hash": "b",
                    "added_on": 1,
                },
            ],
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("providers.qbittorrent.httpx.Client", _client_factory(transport))
    qbit = QbitClient("http://qbit", api_key="qbt_x")
    res = qbit.torrents()
    assert res[0]["name"] == "t1" and res[0]["progress"] == 100.0
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
