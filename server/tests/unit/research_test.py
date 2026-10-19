"""Research: кэш/single-flight поиска, извлечение статей в главы, окно текста."""

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


def test_parse_repo_ref():
    import pytest

    from app.modules.research.github import parse_repo_ref

    assert parse_repo_ref("https://github.com/deepseek-ai/deepseek-harness") == "deepseek-ai/deepseek-harness"
    assert parse_repo_ref("https://github.com/o/r/tree/main/src") == "o/r"
    assert parse_repo_ref("o/r") == "o/r"
    with pytest.raises(ValueError):
        parse_repo_ref("https://gitlab.com/o/r")


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
