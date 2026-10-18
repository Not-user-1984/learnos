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
