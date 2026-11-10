"""Research: кэш/single-flight поиска, извлечение статей в главы, окно текста."""

import time
from types import SimpleNamespace

from bs4 import BeautifulSoup

from app.modules.research.service import ResearchService

HTML = (
    """
<html><head><title>Гайд по observability</title></head>
<body>
<nav>меню мусор</nav>
<script>var x = 1;</script>
<h1>Observability</h1>
<p>Вводный абзац про наблюдаемость: логи, метрики, трейсы и их связь с отладкой распределённых систем.</p>
<h2>Логи</h2>
"""
    + "<p>Структурированные логи важны: уровень, контекст запроса, поток событий сервиса.</p>" * 30
    + """
<h2>Метрики</h2>
"""
    + "<p>Метрики дают агрегаты: RPS, латентности, ошибки. Строй dashboards.</p>" * 30
    + """
<h2>Ссылки</h2>
<p>мелкая секция</p>
<footer>подвал</footer>
</body></html>
"""
)


def make_service(provider) -> ResearchService:
    svc = ResearchService(SimpleNamespace(web_proxy="", search_provider="ddg"))
    svc._provider = provider  # noqa: SLF001 — тест подменяет провайдера
    return svc


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, limit: int) -> dict:
        self.calls += 1
        return {"query": query, "count": 1, "results": [{"title": "t", "url": "https://x", "snippet": "s"}]}


def test_search_cache_single_flight():
    p = FakeProvider()
    svc = make_service(p)
    a = svc.search("kubernetes", 4)
    b = svc.search("kubernetes", 5)  # тот же бакет (<=5)
    c = svc.search("  KUBERNETES ", 5)  # нормализация ключа
    assert a["count"] == 1 and b["count"] == 1 and c["count"] == 1
    assert p.calls == 1
    assert a["provider"] == "fake"
    # другой бакет — отдельный вызов провайдера
    svc.search("kubernetes", 8)
    assert p.calls == 2


def test_window():
    svc = make_service(FakeProvider())
    w = svc.window("a" * 30, offset=10, limit=10)
    assert w["total_chars"] == 30
    assert w["text"] == "a" * 10
    assert w["next_offset"] == 20
    w2 = svc.window("a" * 30, offset=25, limit=10)
    assert w2["next_offset"] is None


def _fake_fetch(url: str):
    return "Гайд по observability", BeautifulSoup(HTML, "html.parser").body


def test_extract_chapters(monkeypatch):
    svc = make_service(FakeProvider())
    monkeypatch.setattr(svc, "_fetch", _fake_fetch)
    page = svc.extract_chapters("https://example.com/guide")
    assert page["title"] == "Гайд по observability"
    titles = [c["title"] for c in page["chapters"]]
    assert "Логи" in titles and "Метрики" in titles
    joined = "\n".join(c["text"] for c in page["chapters"])
    assert "меню мусор" not in joined and "подвал" not in joined and "var x" not in joined
    assert "структурированные" in joined.lower()
    # мелкая секция «Ссылки» приклеена к предыдущей главе
    assert "Ссылки" not in titles


def test_extract(monkeypatch):
    svc = make_service(FakeProvider())
    monkeypatch.setattr(svc, "_fetch", _fake_fetch)
    page = svc.extract("https://x")
    assert page["title"] == "Гайд по observability"
    assert page["chars"] > 100


class _Prov:
    def __init__(self, name, results=None, error=None, raises=False):
        self.name = name
        self._results = results or []
        self._error = error
        self._raises = raises

    def search(self, query, limit):
        if self._raises:
            raise RuntimeError(f"{self.name} упал")
        out = {"query": query, "count": len(self._results), "results": self._results[:limit]}
        if self._error:
            out["error"] = self._error
        return out


class _DelayedProv(_Prov):
    """Провайдер с искусственной задержкой — для проверки параллельности (BB-002)."""

    def __init__(self, name, delay=0.0, results=None, error=None):
        super().__init__(name, results=results, error=error)
        self._delay = delay
        self.calls = 0

    def search(self, query, limit):
        self.calls += 1
        if self._delay:
            time.sleep(self._delay)
        return super().search(query, limit)


def test_chain_falls_to_next_provider():
    from app.modules.research.providers import ChainProvider

    chain = ChainProvider(
        [_Prov("ddg", error="анти-бот"), _Prov("wiki", [{"title": "K8s", "url": "https://x"}])]
    )
    out = chain.search("k8s", 5)
    assert out["provider"] == "chain/wiki"
    assert out["count"] == 1


def test_chain_merges_when_all_empty():
    from app.modules.research.providers import ChainProvider

    chain = ChainProvider([_Prov("ddg", error="202"), _Prov("wiki")])
    out = chain.search("q", 5)
    assert out["count"] == 0
    assert "ddg" in out.get("error", "")


def test_chain_survives_provider_crash():
    from app.modules.research.providers import ChainProvider

    chain = ChainProvider([_Prov("boom", raises=True), _Prov("wiki", [{"title": "t", "url": "u"}])])
    out = chain.search("q", 5)
    assert out["count"] == 1 and out["provider"] == "chain/wiki"


def test_chain_parallel_first_nonempty_wins():
    """BB-002: звенья опрашиваются параллельно — медленное звено не блокирует
    результат быстрого (латентность = самому быстрому живому звену)."""
    from app.modules.research.providers import ChainProvider

    slow = _DelayedProv("ddg", delay=0.4, results=[{"title": "поздно", "url": "https://late"}])
    fast = _DelayedProv("wiki", results=[{"title": "быстро", "url": "https://fast"}])
    chain = ChainProvider([slow, fast])
    t0 = time.monotonic()
    out = chain.search("q", 5)
    elapsed = time.monotonic() - t0
    assert out["provider"] == "chain/wiki" and out["count"] == 1
    assert out["results"][0]["title"] == "быстро"
    assert elapsed < 0.35  # последовательно было бы 0.4+


def test_chain_single_pass_on_empty():
    """BB-002: при полной пустоте звенья опрашиваются ровно один раз —
    повторного сетевого прохода нет, ошибки собраны в error-строку."""
    from app.modules.research.providers import ChainProvider

    ddg = _DelayedProv("ddg", error="ddg 202")
    wiki = _DelayedProv("wiki")
    chain = ChainProvider([ddg, wiki])
    out = chain.search("q", 5)
    assert out["count"] == 0
    assert ddg.calls == 1 and wiki.calls == 1
    assert "ddg" in out.get("error", "")


def test_chain_timeouts_trimmed(monkeypatch):
    """BB-002: короткие таймауты звеньев цепочки (ddg 8 / wiki 6 / hn 6 / tavily 10 / serper 10)."""
    from app.modules.research import providers as P

    captured: dict[str, list] = {"post": [], "get": []}

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {}

    def fake_post(*a, **kw):
        captured["post"].append(kw.get("timeout"))
        return FakeResp()

    def fake_get(*a, **kw):
        captured["get"].append(kw.get("timeout"))
        return FakeResp()

    monkeypatch.setattr(P.httpx, "post", fake_post)
    monkeypatch.setattr(P.httpx, "get", fake_get)
    P.DdgHtmlProvider().search("q", 3)
    P.WikipediaProvider().search("q", 3)
    P.HackerNewsProvider().search("q", 3)
    P.TavilyProvider("k").search("q", 3)
    P.SerperProvider("k").search("q", 3)
    assert captured["post"] == [8, 10, 10]  # ddg, tavily, serper
    assert captured["get"] == [6, 6]  # wikipedia, hackernews
    assert captured["get"] == [6, 6]  # wikipedia, hackernews


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <summary>The dominant sequence transduction models are based on
      complex recurrent networks. We propose a new simple architecture.</summary>
    <published>2017-06-12T17:57:34-07:00</published>
  </entry>
  <entry>
    <title>BERT: Pre-training</title>
    <id>http://arxiv.org/abs/1810.04805v2</id>
    <summary>We introduce BERT.</summary>
    <published>2018-10-11T07:30:21-07:00</published>
  </entry>
</feed>
"""


def test_arxiv_parser(monkeypatch):
    from app.modules.research import providers as P

    class FakeResp:
        status_code = 200
        text = ARXIV_XML

    monkeypatch.setattr(P.httpx, "get", lambda *a, **kw: FakeResp())
    out = P.AcademicProvider().search("transformers", 5)
    assert out["provider"] == "arxiv"
    assert out["count"] == 2
    first = out["results"][0]
    assert first["title"] == "Attention Is All You Need"
    assert first["url"].startswith("http://arxiv.org/abs/")
    assert "2017-06-12" in first["snippet"]


OPENALEX_JSON = {
    "results": [
        {
            "display_name": "Attention Is All You Need",
            "doi": "https://doi.org/10.48550/arXiv.1706.03762",
            "id": "https://openalex.org/W2963403868",
            "publication_year": 2017,
            "cited_by_count": 118000,
            "open_access": {"is_oa": True},
            "authorships": [
                {"author": {"display_name": "Ashish Vaswani"}},
                {"author": {"display_name": "Noam Shazeer"}},
            ],
            "abstract_inverted_index": {"attention": [0, 4], "is": [1], "all": [2], "you": [3], "need": [5]},
        },
        {
            "display_name": "BERT: Pre-training of Deep Bidirectional Transformers",
            "doi": None,
            "id": "https://openalex.org/W2963403870",
            "publication_year": 2018,
            "cited_by_count": 60000,
            "open_access": {"is_oa": False},
            "authorships": [],
            "abstract_inverted_index": None,
        },
    ]
}


def test_openalex_parser(monkeypatch):
    from app.modules.research import providers as P

    class FakeResp:
        status_code = 200

        def json(self):
            return OPENALEX_JSON

    monkeypatch.setattr(P.httpx, "get", lambda *a, **kw: FakeResp())
    out = P.OpenAlexProvider().search("transformer", 5)
    assert out["provider"] == "openalex"
    assert out["count"] == 2
    first = out["results"][0]
    assert first["title"] == "Attention Is All You Need"
    assert first["url"] == "https://doi.org/10.48550/arXiv.1706.03762"
    assert first["snippet"] == "attention is all you attention need"
    assert "Vaswani" in first["authors"]
    assert first["year"] == 2017 and first["citations"] == 118000 and first["open_access"] is True
    assert out["results"][1]["url"].startswith("https://openalex.org/")
    assert out["results"][1]["snippet"] == ""


def test_openalex_http_error(monkeypatch):
    from app.modules.research import providers as P

    class FakeResp:
        status_code = 503

    monkeypatch.setattr(P.httpx, "get", lambda *a, **kw: FakeResp())
    out = P.OpenAlexProvider().search("q", 5)
    assert out["count"] == 0 and "openalex 503" in out["error"]


S2_JSON = {
    "data": [
        {
            "title": "Attention Is All You Need",
            "url": "https://www.semanticscholar.org/paper/1706.03762",
            "abstract": "  The dominant sequence   transduction models.  ",
            "year": 2017,
            "citationCount": 90000,
            "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
            "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
        },
        {
            "title": "A Survey of Transformers",
            "url": "https://www.semanticscholar.org/paper/survey",
            "abstract": None,
            "year": 2021,
            "citationCount": 1000,
            "authors": [],
            "openAccessPdf": None,
        },
    ]
}


def test_semantic_scholar_parser(monkeypatch):
    from app.modules.research import providers as P

    class FakeResp:
        status_code = 200

        def json(self):
            return S2_JSON

    monkeypatch.setattr(P.httpx, "get", lambda *a, **kw: FakeResp())
    out = P.SemanticScholarProvider().search("transformer", 5)
    assert out["provider"] == "semantic_scholar"
    first = out["results"][0]
    assert first["url"] == "https://arxiv.org/pdf/1706.03762"  # открытый PDF приоритетнее
    assert first["snippet"] == "The dominant sequence transduction models."
    assert first["citations"] == 90000 and first["open_access"] is True
    assert out["results"][1]["open_access"] is False
    assert out["results"][1]["url"].endswith("/survey")


def test_semantic_scholar_retry_on_429(monkeypatch):
    """429 (shared pool без ключа): один ретрай с паузой, потом результат."""
    from app.modules.research import providers as P

    calls = {"n": 0}

    class RateLimited:
        status_code = 429

    class Ok:
        status_code = 200

        def json(self):
            return S2_JSON

    def fake_get(*a, **kw):
        calls["n"] += 1
        return RateLimited() if calls["n"] == 1 else Ok()

    sleeps = []
    monkeypatch.setattr(P.httpx, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    out = P.SemanticScholarProvider().search("q", 5)
    assert calls["n"] == 2 and sleeps == [2]
    assert out["count"] == 2


def test_semantic_scholar_429_twice_gives_up(monkeypatch):
    from app.modules.research import providers as P

    class RateLimited:
        status_code = 429

    monkeypatch.setattr(P.httpx, "get", lambda *a, **kw: RateLimited())
    monkeypatch.setattr("time.sleep", lambda s: None)
    out = P.SemanticScholarProvider().search("q", 5)
    assert out["count"] == 0 and "429" in out["error"]


def _academic_service(providers) -> ResearchService:
    svc = ResearchService(SimpleNamespace(web_proxy="", search_provider="ddg"))
    svc._academic_providers = providers  # noqa: SLF001 — тест подменяет академических провайдеров
    return svc


def test_academic_aggregates_and_dedups(monkeypatch):
    """arXiv+OpenAlex+S2: дедуп по DOI/title, у каждого результата provider, смешение по кругу."""
    arxiv = _Prov(
        "arxiv", [{"title": "Attention Is All You Need", "url": "https://arxiv.org/abs/1706.03762"}]
    )
    openalex = _Prov(
        "openalex",
        [
            {
                "title": "Attention Is All You Need",  # дубликат по заголовку
                "url": "https://doi.org/10.48550/arXiv.1706.03762",
            },
            {
                "title": "Scaling Laws for Neural Language Models",
                "url": "https://openalex.org/W1",
                "doi": "10.1/x",
            },
        ],
    )
    s2 = _Prov(
        "semantic_scholar",
        [{"title": "A Survey of Transformers", "url": "https://s2/survey", "doi": "https://doi.org/10.1/x"}],
    )  # дубликат по DOI работы openalex
    svc = _academic_service([arxiv, openalex, s2])
    out = svc.academic("transformer attention", 5)
    titles = [r["title"] for r in out["results"]]
    # круг 0: arxiv-Attention взят, openalex-Attention откинут (title-дубль), s2-Survey взят;
    # круг 1: openalex-Scaling Laws откинут — DOI уже занят записью s2
    assert titles == ["Attention Is All You Need", "A Survey of Transformers"]
    assert all("provider" in r for r in out["results"])
    assert {r["provider"] for r in out["results"]} == {"arxiv", "semantic_scholar"}
    # сводка считает «сколько нашёл каждый» до дедупа
    assert out["providers"]["arxiv"] == 1
    assert out["providers"]["openalex"] == 2
    assert out["providers"]["semantic_scholar"] == 1
    assert "failed" not in out["providers"]
    # верхний уровень: агрегатный провайдер + кэш по новому ключу
    assert out["provider"] == "academic"


def test_academic_survives_provider_crash(monkeypatch):
    arxiv = _Prov("arxiv", [{"title": "Attention", "url": "https://arxiv.org/abs/1"}])
    boom = _Prov("openalex", raises=True)
    err = _Prov("semantic_scholar", error="semantic_scholar 429")
    svc = _academic_service([arxiv, boom, err])
    out = svc.academic("q", 5)
    assert out["count"] == 1
    assert out["results"][0]["provider"] == "arxiv"
    assert "openalex упал" in " ".join(out["providers"]["failed"])
    assert any("429" in f for f in out["providers"]["failed"])


def test_academic_limit_applies_to_merged(monkeypatch):
    """Лимит режет уже смешанную выдачу, а не выдачу каждого провайдера."""
    a = _Prov("arxiv", [{"title": f"A{i}", "url": f"https://a/{i}"} for i in range(4)])
    o = _Prov("openalex", [{"title": f"O{i}", "url": f"https://o/{i}"} for i in range(4)])
    svc = _academic_service([a, o])
    out = svc.academic("q", 2)  # бакет <=5 → limit 5... берём 5
    assert out["count"] == 5
    # чередование: arxiv и openalex идут вперемешку
    assert [r["provider"] for r in out["results"][:4]] == ["arxiv", "openalex", "arxiv", "openalex"]


def test_academic_agg_parallel():
    """BB-002: arXiv/OpenAlex/S2 опрашиваются параллельно — латентность = max
    звеньев, а не сумма; порядок групп и сводка counts не меняются."""
    provs = [
        _DelayedProv("arxiv", delay=0.3, results=[{"title": "A", "url": "https://a"}]),
        _DelayedProv("openalex", delay=0.3, results=[{"title": "O", "url": "https://o"}]),
        _DelayedProv("semantic_scholar", delay=0.3, results=[{"title": "S", "url": "https://s"}]),
    ]
    svc = _academic_service(provs)
    t0 = time.monotonic()
    out = svc.academic("параллельность агрегата", 5)
    elapsed = time.monotonic() - t0
    assert out["count"] == 3
    assert out["providers"] == {"arxiv": 1, "openalex": 1, "semantic_scholar": 1}
    assert elapsed < 0.75  # последовательно было бы ~0.9


def test_providers_view_chain_and_keys(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    svc = ResearchService(SimpleNamespace(web_proxy="", search_provider="chain"))
    view = svc.providers_view()
    assert view["web"]["mode"] == "chain"
    names = [p["name"] for p in view["web"]["providers"]]
    assert names == ["tavily", "ddg", "wikipedia", "hackernews"]
    assert any("ключ задан" in p["note"] for p in view["web"]["providers"])
    assert [p["name"] for p in view["academic"]["providers"]] == [
        "arxiv",
        "openalex",
        "semantic_scholar",
    ]
    assert all(p["enabled"] for p in view["academic"]["providers"])
    assert [p["name"] for p in view["video"]["providers"]] == ["youtube"]


def test_providers_view_explicit_provider(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    svc = ResearchService(SimpleNamespace(web_proxy="", search_provider="wikipedia"))
    view = svc.providers_view()
    assert view["web"]["mode"] == "single"
    enabled = {p["name"]: p["enabled"] for p in view["web"]["providers"]}
    assert enabled == {"ddg": False, "wikipedia": True, "hackernews": False}


def test_search_providers_tool(container):
    """Тул search_providers зарегистрирован в research и отдаёт категории web/academic/video."""
    from app.kernel.tools.spec import ToolContext

    tool = container.tools.get("search_providers")
    assert tool.module == "research"
    out = container.tools.call("search_providers", {}, ToolContext())
    assert {"web", "academic", "video"} <= set(out)
    assert "openalex" in [p["name"] for p in out["academic"]["providers"]]


def test_parse_repo_ref():
    import pytest

    from app.modules.research.github import parse_repo_ref

    assert parse_repo_ref("https://github.com/deepseek-ai/deepseek-harness") == "deepseek-ai/deepseek-harness"
    assert parse_repo_ref("https://github.com/o/r/tree/main/src") == "o/r"
    assert parse_repo_ref("o/r") == "o/r"
    with pytest.raises(ValueError):
        parse_repo_ref("https://gitlab.com/o/r")


def test_academic_providers_pick_up_proxy():
    """OpenAlex/S2 идут через настроенный прокси (S2 режет датацентровые IP), arXiv — напрямую."""
    svc = ResearchService(SimpleNamespace(web_proxy="socks5://xray:1080", search_provider="chain"))
    arxiv, openalex, s2 = svc._academic_providers  # noqa: SLF001 — проверка сборки сервиса
    assert getattr(openalex, "_proxy", None) == "socks5://xray:1080"
    assert getattr(s2, "_proxy", None) == "socks5://xray:1080"
    assert not hasattr(arxiv, "_proxy") or arxiv._proxy is None  # noqa: SLF001
    # прокси сменился — пересборка подхватывает новый
    svc._settings = SimpleNamespace(web_proxy="", search_provider="chain")
    assert svc._build_academic()[1]._proxy is None  # noqa: SLF001


def test_vless_to_config_reality():
    from app.modules.research.connectivity import vless_to_config

    link = (
        "vless://01234567-89ab-cdef-0123-456789abcdef@nl.example.com:443"
        "?encryption=none&security=reality&sni=www.example.com&fp=chrome&pbk=PUBKEY&sid=ab12&type=tcp&flow=xtls-rprx-vision"
    )
    cfg = vless_to_config(link)
    ob = cfg["outbounds"][0]
    assert ob["protocol"] == "vless"
    vnext = ob["settings"]["vnext"][0]
    assert vnext["address"] == "nl.example.com" and vnext["port"] == 443
    assert vnext["users"][0]["id"] == "01234567-89ab-cdef-0123-456789abcdef"
    assert vnext["users"][0]["flow"] == "xtls-rprx-vision"
    st = ob["streamSettings"]
    assert st["security"] == "reality" and st["realitySettings"]["publicKey"] == "PUBKEY"
    assert cfg["inbounds"][0]["protocol"] == "socks" and cfg["inbounds"][0]["port"] == 1080


def test_vless_to_config_ws_tls():
    from app.modules.research.connectivity import vless_to_config

    link = "vless://01234567-89ab-cdef-0123-456789abcdef@h.example.org:8443?type=ws&security=tls&sni=cdn.example&path=%2Fws"
    cfg = vless_to_config(link)
    st = cfg["outbounds"][0]["streamSettings"]
    assert st["network"] == "ws" and st["wsSettings"]["path"] == "/ws"
    assert st["security"] == "tls" and st["tlsSettings"]["serverName"] == "cdn.example"


def test_vless_invalid_link():
    import pytest

    from app.modules.research.connectivity import vless_to_config

    with pytest.raises(ValueError):
        vless_to_config("https://example.com/not-vless")


def test_connectivity_apply_and_proxy_priority():
    from types import SimpleNamespace

    from app.modules.research.connectivity import apply_to_settings, effective_proxy, masked

    s = SimpleNamespace(search_provider="chain", web_proxy="", yt_proxy="", telegram_proxy="")
    out = apply_to_settings(
        s, {"search_provider": "tavily", "search_api_key": "tvly-xyz", "vless_key": "vless://..."}
    )
    assert out["proxy"].startswith("socks5://xray")
    assert s.web_proxy == "socks5://xray:1080" and s.telegram_proxy.startswith("socks5://xray")

    assert effective_proxy({"proxy_url": "socks5://1.2.3.4:1080"}, "old") == "socks5://1.2.3.4:1080"
    assert effective_proxy({}, "old-env-proxy") == "old-env-proxy"

    m = masked(
        {
            "search_api_key": "tvly-abcdef123456",
            "vless_key": "",
            "proxy_url": "x",
            "search_provider": "tavily",
        }
    )
    assert "…" in m["search_api_key"] and m["has_vless_key"] is False


def test_vless_to_config_xhttp_reality():
    """Нод пользователя: VLESS+Reality+XHTTP (mihomo-профиль vless-nl)."""
    from app.modules.research.connectivity import vless_to_config

    link = (
        "vless://01234567-89ab-cdef-0123-456789abcdef@132.243.123.172:443"
        "?type=xhttp&security=reality&sni=www.bol.com&fp=firefox&pbk=PUB&sid=a29f&path=%2Fsearch&mode=auto"
    )
    cfg = vless_to_config(link)
    st = cfg["outbounds"][0]["streamSettings"]
    assert st["network"] == "xhttp"
    assert st["xhttpSettings"]["path"] == "/search"
    assert st["xhttpSettings"]["mode"] == "auto"
    assert st["security"] == "reality"
    assert st["realitySettings"]["serverName"] == "www.bol.com"
    assert st["realitySettings"]["fingerprint"] == "firefox"
