"""Провайдеры веб-поиска: единый контракт + цепочка с автовыбором.

Реалии 2026: ключевые бесплатные HTML-поисковики (DDG, Bing, Mojeek) отдают анти-бот
из бытовых сетей. Поэтому:
- web_search идёт по цепочке [платный по ключу → ddg → wikipedia → hackernews] и
  почти всегда даёт хотя бы что-то осмысленное;
- научные статьи — агрегат трёх ключлесс-API: arXiv (препринты), OpenAlex
  (библиография), Semantic Scholar (цитирования) — см. ResearchService.academic;
- платные (Tavily/Serper) включаются автоматически при наличии ключа в env —
  это рекомендуемый апгрейд качества выдачи (см. T-019).
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

log = logging.getLogger("learnos.research")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)


class SearchProvider(Protocol):
    """Контракт поискового провайдера (см. паттерн Hermes web_search_registry)."""

    name: str

    def search(self, query: str, limit: int) -> dict[str, Any]: ...


def _ok(query: str, results: list[dict], provider: str) -> dict[str, Any]:
    return {"query": query, "count": len(results), "results": results, "provider": provider}


class DdgHtmlProvider:
    """DuckDuckGo html-эндпоинт: без ключей; капризен (анти-бот) — в цепочке первым,
    при пустом ответе ход переходит следующему провайдеру."""

    name = "ddg"

    def __init__(self, proxy: str = "") -> None:
        self._proxy = proxy or None

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": UA},
            timeout=15,
            follow_redirects=True,
            proxy=self._proxy,
        )
        if r.status_code != 200 or "result__a" not in r.text:
            return {"query": query, "count": 0, "results": [], "error": f"ddg status {r.status_code}"}
        blocks = re.split(r'<div[^>]+class="[^"]*result[^"]*"', r.text)[1:]
        results = []
        for b in blocks:
            m = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b)
            if not m:
                continue
            url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
            if "uddg=" in url:
                url = parse_qs(urlparse(url).query).get("uddg", [url])[0]
            sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', b, re.S)
            snippet = re.sub(r"<[^>]+>", "", sn.group(1)).strip() if sn else ""
            results.append({"title": unquote(title).strip(), "url": unquote(url), "snippet": snippet[:200]})
            if len(results) >= limit:
                break
        return _ok(query, results, self.name)


class WikipediaProvider:
    """MediaWiki search API: стабильный ключлесс, энциклопедические основы темы."""

    name = "wikipedia"

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.get(
            "https://ru.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(limit, 10),
                "srprop": "snippet",
                "format": "json",
            },
            headers={"User-Agent": f"LearnOS/0.1 ({UA})"},
            timeout=10,
        )
        hits = (r.json().get("query") or {}).get("search") or []
        results = [
            {
                "title": h.get("title", ""),
                "url": f"https://ru.wikipedia.org/wiki/{quote_plus(h.get('title', '').replace(' ', '_'))}",
                "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", ""))[:200],
            }
            for h in hits[:limit]
        ]
        return _ok(query, results, self.name)


class HackerNewsProvider:
    """HN Algolia API: практики, обсуждения, туториалы — без ключей."""

    name = "hackernews"

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "hitsPerPage": min(limit, 10), "tags": "story"},
            headers={"User-Agent": UA},
            timeout=10,
        )
        hits = r.json().get("hits") or []
        results = []
        for h in hits[:limit]:
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            results.append(
                {
                    "title": h.get("title") or "",
                    "url": url,
                    "snippet": f"обсуждение: {h.get('points', 0)}↑ {h.get('num_comments', 0)} комм.",
                }
            )
        return _ok(query, results, self.name)


class AcademicProvider:
    """arXiv API: научные статьи (препринты) — стабильно, без ключей и капч."""

    name = "arxiv"

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "max_results": min(limit, 10)},
            headers={"User-Agent": UA},
            timeout=15,
        )
        ns = {"a": "http://www.w3.org/2005/Atom"}
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            return {"query": query, "count": 0, "results": [], "error": "arxiv xml parse"}
        results = []
        for e in root.findall("a:entry", ns):
            title = (e.findtext("a:title", "", ns) or "").strip()
            url = (e.findtext("a:id", "", ns) or "").strip()
            summary = re.sub(r"\s+", " ", e.findtext("a:summary", "", ns) or "").strip()
            published = (e.findtext("a:published", "", ns) or "")[:10]
            results.append({"title": title, "url": url, "snippet": f"{published} · {summary[:180]}"})
            if len(results) >= limit:
                break
        return _ok(query, results, self.name)


def reconstruct_abstract(inverted: dict | None) -> str:
    """OpenAlex abstract_inverted_index → обычный текст (слово → позиции в тексте)."""
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[int(i)] = word
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexProvider:
    """OpenAlex: открытая библиография всех научных работ, ~100k запросов/день без ключа."""

    name = "openalex"

    def __init__(self, proxy: str = "") -> None:
        self._proxy = proxy or None

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": min(limit, 10)},
            headers={"User-Agent": UA},
            timeout=15,
            proxy=self._proxy,
        )
        if r.status_code != 200:
            return {"query": query, "count": 0, "results": [], "error": f"openalex {r.status_code}"}
        results = []
        for w in (r.json().get("results") or [])[:limit]:
            authors = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in (w.get("authorships") or [])[:3]
                if a.get("author", {}).get("display_name")
            )
            abstract = reconstruct_abstract(w.get("abstract_inverted_index"))
            results.append(
                {
                    "title": w.get("display_name", ""),
                    "url": w.get("doi") or w.get("id", ""),
                    "snippet": abstract[:200],
                    "authors": authors,
                    "year": w.get("publication_year"),
                    "citations": w.get("cited_by_count"),
                    "open_access": bool((w.get("open_access") or {}).get("is_oa")),
                }
            )
        return _ok(query, results, self.name)


class SemanticScholarProvider:
    """Semantic Scholar: статьи + метрики цитирования. Без ключа ~1 rps (shared pool):
    429 терпим одним ретраем с паузой, дальше тихий пропуск."""

    name = "semantic_scholar"

    def __init__(self, proxy: str = "") -> None:
        self._proxy = proxy or None

    def search(self, query: str, limit: int) -> dict[str, Any]:
        import time

        params = {
            "query": query,
            "limit": min(limit, 10),
            "fields": "title,authors,year,abstract,url,openAccessPdf,citationCount",
        }
        for attempt in range(2):
            r = httpx.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                headers={"User-Agent": UA},
                timeout=15,
                proxy=self._proxy,
            )
            if r.status_code == 429 and attempt == 0:
                time.sleep(2)
                continue
            break
        if r.status_code != 200:
            return {"query": query, "count": 0, "results": [], "error": f"semantic_scholar {r.status_code}"}
        results = []
        for p in (r.json().get("data") or [])[:limit]:
            pdf = (p.get("openAccessPdf") or {}).get("url") or ""
            abstract = re.sub(r"\s+", " ", p.get("abstract") or "").strip()
            results.append(
                {
                    "title": p.get("title", ""),
                    "url": pdf or p.get("url", ""),
                    "snippet": abstract[:200],
                    "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3]),
                    "year": p.get("year"),
                    "citations": p.get("citationCount"),
                    "open_access": bool(pdf),
                }
            )
        return _ok(query, results, self.name)


class TavilyProvider:
    """Tavily: LLM-ориентированный поиск, ~1000 кредитов/мес бесплатно. Ключ TAVILY_API_KEY."""

    name = "tavily"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": self._key, "query": query, "max_results": limit, "search_depth": "basic"},
            headers={"User-Agent": UA},
            timeout=20,
        )
        data = r.json()
        if r.status_code != 200:
            return {"query": query, "count": 0, "results": [], "error": f"tavily {r.status_code}"}
        results = [
            {
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "snippet": (it.get("content") or "")[:200],
            }
            for it in (data.get("results") or [])[:limit]
        ]
        return _ok(query, results, self.name)


class SerperProvider:
    """Serper.dev: Google-выдача в JSON, 2500 запросов бесплатно на старте. Ключ SERPER_API_KEY."""

    name = "serper"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": limit},
            headers={"X-API-KEY": self._key, "User-Agent": UA},
            timeout=20,
        )
        data = r.json()
        if r.status_code != 200:
            return {"query": query, "count": 0, "results": [], "error": f"serper {r.status_code}"}
        results = []
        for it in (data.get("organic") or [])[:limit]:
            results.append(
                {
                    "title": it.get("title", ""),
                    "url": it.get("link", ""),
                    "snippet": (it.get("snippet") or "")[:200],
                }
            )
        return _ok(query, results, self.name)


class ChainProvider:
    """Ключлесс-спасение (паттерн Hermes): пробуем провайдеров по очереди до
    первого непустого ответа; работающие смешиваются (top-N от каждого)."""

    name = "chain"

    def __init__(self, providers: list[SearchProvider]) -> None:
        self._providers = providers

    def search(self, query: str, limit: int) -> dict[str, Any]:
        errors = []
        for p in self._providers:
            try:
                out = p.search(query, limit)
            except Exception as e:  # noqa: BLE001 — цепочка должна пережить падение звена
                errors.append(f"{p.name}: {e}")
                continue
            if out.get("count"):
                out["provider"] = f"{self.name}/{p.name}"
                return out
            if out.get("error"):
                errors.append(f"{p.name}: {out['error']}")
        # полная пустота — смешиваем всё что есть
        merged: list[dict] = []
        for p in self._providers:
            try:
                merged.extend(p.search(query, limit).get("results") or [])
            except Exception:  # noqa: BLE001
                continue
        out = _ok(query, merged[:limit], self.name)
        if not merged and errors:
            out["error"] = "; ".join(errors)[:200]
        return out


def build_provider(settings) -> SearchProvider:
    """Активный провайдер: явный LEARNOS_SEARCH_PROVIDER или цепочка с автовыбором
    платного по наличию ключа (TAVILY_API_KEY / SERPER_API_KEY)."""
    import os

    name = (getattr(settings, "search_provider", "") or "").lower()
    proxy = getattr(settings, "web_proxy", "") or ""

    def wiki() -> WikipediaProvider:
        return WikipediaProvider()

    def hn() -> HackerNewsProvider:
        return HackerNewsProvider()

    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    serper_key = os.environ.get("SERPER_API_KEY", "")

    if name == "ddg":
        return DdgHtmlProvider(proxy)
    if name == "wikipedia":
        return wiki()
    if name == "hackernews":
        return hn()
    if name == "arxiv":
        return AcademicProvider()
    if name == "tavily":
        if not tavily_key:
            raise ValueError("TAVILY_API_KEY не задан")
        return TavilyProvider(tavily_key)
    if name == "serper":
        if not serper_key:
            raise ValueError("SERPER_API_KEY не задан")
        return SerperProvider(serper_key)
    if name == "chain" or not name:
        chain: list[SearchProvider] = []
        if serper_key:
            chain.append(SerperProvider(serper_key))
        elif tavily_key:
            chain.append(TavilyProvider(tavily_key))
        chain.extend([DdgHtmlProvider(proxy), wiki(), hn()])
        return ChainProvider(chain)
    raise ValueError(
        f"неизвестный поисковый провайдер '{name}' "
        "(доступны: chain, ddg, wikipedia, hackernews, arxiv, tavily, serper)"
    )
