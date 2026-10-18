"""Сервис research: поиск с кэшем и single-flight, извлечение страниц в текст/главы.

Truncate-and-store (паттерн Hermes): агенту — окно текста с next_offset,
полный текст живёт в главах источника kind=web в библиотеке.
"""

import logging
import re
import threading
import time
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from .providers import UA, AcademicProvider, build_provider

log = logging.getLogger("learnos.research")

_TTL = 20 * 60  # кэш поиска, секунд
_SKIP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "iframe")
_MIN_CHAPTER_CHARS = 400  # мельче — приклеиваем к соседней главе


@dataclass
class _CacheEntry:
    value: dict
    expires: float


class ResearchService:
    """Поиск и извлечение страниц для агентов и библиотеки."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._provider = build_provider(settings)
        self._academic = AcademicProvider()
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # --- поиск ---

    def search(self, query: str, limit: int = 6) -> dict:
        """Поиск с кэшем (TTL 20 мин) и single-flight: одинаковые запросы делят один вызов."""
        return self._cached(f"{self._provider.name}", query, limit, self._provider.search)

    def academic(self, query: str, limit: int = 6) -> dict:
        """Научные статьи (arXiv) с тем же кэшем и single-flight."""
        return self._cached("arxiv", query, limit, self._academic.search)

    def _cached(self, provider_key: str, query: str, limit: int, fn) -> dict:
        limit = max(1, min(10, int(limit)))
        bucket = 5 if limit <= 5 else 10
        key = f"{provider_key}:{bucket}:{query.strip().lower()}"
        with self._guard:
            entry = self._cache.get(key)
            if entry and entry.expires > time.monotonic():
                return entry.value
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            with self._guard:
                entry = self._cache.get(key)
                if entry and entry.expires > time.monotonic():
                    return entry.value
            result = fn(query, bucket)
            result.setdefault("provider", provider_key)
            with self._guard:
                self._cache[key] = _CacheEntry(result, time.monotonic() + _TTL)
                self._locks.pop(key, None)
            return result

    # --- извлечение страницы ---

    def _fetch(self, url: str) -> tuple[str, object]:
        """Страница → (title, очищенный root-узел). Title достаём до среза body/main."""
        r = httpx.get(
            url,
            headers={"User-Agent": UA},
            timeout=25,
            follow_redirects=True,
            proxy=(getattr(self._settings, "web_proxy", "") or "") or None,
        )
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "xml" not in ctype:
            raise ValueError(f"не HTML-страница (content-type: {ctype or 'неизвестен'})")
        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.get_text(strip=True) if soup.title and soup.title.string else "")[:200]
        for tag in soup.find_all(_SKIP_TAGS):
            tag.decompose()
        root = soup.body or soup
        for sel in ("main", "article"):
            node = root.find(sel)
            if node is not None and len(node.get_text(strip=True)) > 500:
                root = node
                break
        return title, root

    def extract(self, url: str) -> dict:
        """Страница → {title, text, chars} одним куском (для коротких страниц/превью)."""
        title, root = self._fetch(url)
        text = _normalize(root.get_text("\n"))
        return {"title": title, "text": text, "chars": len(text)}

    def window(self, text: str, offset: int = 0, limit: int = 12000) -> dict:
        """Окно текста для контекста агента: {text, next_offset, total_chars}."""
        chunk = text[offset : offset + limit]
        return {
            "text": chunk,
            "offset": offset,
            "total_chars": len(text),
            "next_offset": offset + limit if offset + limit < len(text) else None,
        }

    def extract_chapters(self, url: str, max_chapters: int = 30) -> dict:
        """Страница → {title, chapters:[{title,text}]} по заголовкам h1/h2.

        Мелкие секции приклеиваются к предыдущей главе; оглавление без контента не главa.
        """
        page_title, root = self._fetch(url)

        raw: list[tuple[str, str]] = []
        current_title = page_title or "Статья"
        buf: list[str] = []

        def flush() -> None:
            text = _normalize("\n".join(buf))
            if text:
                raw.append((current_title, text))
            buf.clear()

        for el in root.descendants:
            if getattr(el, "name", None) in ("h1", "h2"):
                flush()
                current_title = el.get_text(" ", strip=True)[:120] or current_title
            elif getattr(el, "name", None) == "p":
                line = el.get_text(" ", strip=True)
                if line:
                    buf.append(line)
        flush()

        chapters: list[dict] = []
        for title, text in raw:
            if chapters and len(text) < _MIN_CHAPTER_CHARS:
                chapters[-1]["text"] += "\n\n" + text
            else:
                chapters.append({"title": title, "text": text})
        # слишком длинный хвост мелочи — укрупняем до лимита
        while len(chapters) > max_chapters:
            chapters[-2]["text"] += "\n\n" + chapters[-1]["text"]
            chapters.pop()
        if not chapters:
            raise ValueError("на странице не найден текст статьи (возможно, JS-рендер — см. браузер, T-015)")
        return {"title": page_title, "chapters": chapters}


def _normalize(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
