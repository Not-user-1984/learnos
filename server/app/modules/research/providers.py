"""Провайдеры веб-поиска: единый контракт + реестр с автовыбором.

Бесплатный старт — DDG (html-эндпоинт, без ключей). Задел под платных:
класс провайдера + запись в PROVIDERS, выбор через LEARNOS_SEARCH_PROVIDER.
"""

import logging
import re
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlparse

import httpx

log = logging.getLogger("learnos.research")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)


class SearchProvider(Protocol):
    """Контракт поискового провайдера (см. паттерн Hermes web_search_registry)."""

    name: str

    def search(self, query: str, limit: int) -> dict[str, Any]: ...


class DdgHtmlProvider:
    """DuckDuckGo html-эндпоинт: без ключей; через прокси при блокировке региона."""

    name = "ddg"

    def __init__(self, proxy: str = "") -> None:
        self._proxy = proxy or None

    def search(self, query: str, limit: int) -> dict[str, Any]:
        r = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": UA},
            timeout=20,
            follow_redirects=True,
            proxy=self._proxy,
        )
        if r.status_code != 200 or "result__a" not in r.text:
            return {
                "query": query,
                "count": 0,
                "results": [],
                "error": f"ddg status {r.status_code}, возможно анти-бот или блокировка региона",
            }
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
        return {"query": query, "count": len(results), "results": results}


def build_provider(settings) -> SearchProvider:
    """Активный провайдер: явный LEARNOS_SEARCH_PROVIDER, дефолт — бесплатный ddg."""
    name = (getattr(settings, "search_provider", "") or "ddg").lower()
    proxy = getattr(settings, "web_proxy", "") or ""
    if name == "ddg":
        return DdgHtmlProvider(proxy)
    raise ValueError(f"неизвестный поисковый провайдер '{name}' (доступен: ddg; платные — по ключам, T-014)")
