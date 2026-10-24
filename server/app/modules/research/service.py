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

from .providers import (
    UA,
    AcademicProvider,
    OpenAlexProvider,
    SemanticScholarProvider,
    build_provider,
)

log = logging.getLogger("learnos.research")

_TTL = 20 * 60  # кэш поиска, секунд
_SKIP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "iframe")
_MIN_CHAPTER_CHARS = 400  # мельче — приклеиваем к соседней главе


def _norm_doi(item: dict) -> str:
    """Нормализованный DOI для дедупа (без схемы и префикса doi.org)."""
    doi = str(item.get("doi") or "")
    return doi.lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip()


def _norm_title(title: str) -> str:
    """Нормализованный заголовок: нижний регистр, без пунктуации и пробелов."""
    return re.sub(r"[^a-zа-яё0-9]+", "", (title or "").lower())


def _interleave(groups: list[list[dict]], limit: int) -> list[dict]:
    """Смешать выдачи провайдеров по кругу (round-robin) с дедупом на лету:
    дубли ловятся по нормализованному DOI, иначе по нормализованному заголовку."""
    merged: list[dict] = []
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    idx = 0
    while len(merged) < limit:
        took = False
        for g in groups:
            if idx >= len(g):
                continue
            took = True
            item = g[idx]
            doi = _norm_doi(item)
            title_key = _norm_title(item.get("title", ""))
            if doi:
                if doi in seen_doi:
                    continue
                seen_doi.add(doi)
            elif title_key:
                if title_key in seen_title:
                    continue
                seen_title.add(title_key)
            merged.append(item)
            if len(merged) >= limit:
                break
        if not took:
            break
        idx += 1
    return merged


@dataclass
class _CacheEntry:
    value: dict
    expires: float


class ResearchService:
    """Поиск и извлечение страниц для агентов и библиотеки."""

    def __init__(self, settings, uow=None) -> None:
        self._settings = settings
        self._uow = uow
        self._provider = build_provider(settings)
        self._academic_providers = [AcademicProvider(), OpenAlexProvider(), SemanticScholarProvider()]
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # --- настройки связи (UI: поиск/прокси/vless) ---

    def refresh_connectivity(self) -> dict:
        """Загрузить настройки из БД, применить к Settings и пересобрать провайдера."""
        from .connectivity import apply_to_settings, load_connectivity

        if self._uow is None:
            return {}
        values = load_connectivity(self._uow)
        applied = apply_to_settings(self._settings, values)
        self._provider = build_provider(self._settings)
        with self._guard:
            self._cache.clear()  # сменился провайдер — кэш неактуален
        return applied

    def apply_connectivity(self, patch: dict) -> dict:
        """Сохранить + применить настройки связи (PUT из UI)."""
        from .connectivity import masked, save_connectivity, write_xray_config

        clean = save_connectivity(self._uow, patch)
        if clean.get("vless_key"):
            write_xray_config(clean["vless_key"], self._settings.data_dir)
        applied = self.refresh_connectivity()
        return {"applied": applied, "stored": masked(clean)}

    def connectivity_view(self) -> dict:
        from .connectivity import load_connectivity, masked

        return masked(load_connectivity(self._uow))

    def connectivity_check(self) -> dict:
        """Быстрая диагностика: поиск, YouTube, внешний IP (через прокси при наличии)."""
        out: dict = {"proxy": self._settings.web_proxy or "(без прокси)"}
        try:
            r = self.search("docker documentation", 3)
            out["web_search"] = f"{r.get('provider')}: {r.get('count')} рез-тов"
        except Exception as e:  # noqa: BLE001
            out["web_search"] = f"ошибка: {str(e)[:80]}"
        try:
            import subprocess

            cmd = [
                "yt-dlp",
                "ytsearch1:test",
                "--flat-playlist",
                "--no-warnings",
                "--retries",
                "1",
                "--socket-timeout",
                "6",
                "--print",
                "%(id)s",
            ]
            if self._settings.yt_proxy:
                cmd[1:1] = ["--proxy", self._settings.yt_proxy]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out["youtube"] = "ok" if (r.returncode == 0 and r.stdout.strip()) else "недоступен"
        except Exception:  # noqa: BLE001
            out["youtube"] = "таймаут"
        try:
            ip = httpx.get(
                "https://api.ipify.org",
                timeout=10,
                proxy=self._settings.web_proxy or None,
            ).text
            out["external_ip"] = ip
        except Exception:  # noqa: BLE001
            out["external_ip"] = "недоступен"
        return out

    # --- поиск ---

    def search(self, query: str, limit: int = 6) -> dict:
        """Поиск с кэшем (TTL 20 мин) и single-flight: одинаковые запросы делят один вызов."""
        return self._cached(f"{self._provider.name}", query, limit, self._provider.search)

    def academic(self, query: str, limit: int = 6) -> dict:
        """Научные статьи: arXiv + OpenAlex + Semantic Scholar с дедупом и смешиванием.

        Падение одного провайдера не роняет остальные — попадает в providers.failed.
        У каждой статьи поле provider; сверху сводка {"arxiv": n, "openalex": n, ...}.
        """
        return self._cached("academic", query, limit, self._academic_agg)

    def _academic_agg(self, query: str, limit: int) -> dict:
        groups: list[list[dict]] = []
        counts: dict[str, int] = {}
        failed: list[str] = []
        for p in self._academic_providers:
            try:
                out = p.search(query, limit)
            except Exception as e:  # noqa: BLE001 — один провайдер не роняет агрегацию
                failed.append(f"{p.name}: {str(e)[:120]}")
                out = {}
            if out.get("error"):
                failed.append(f"{p.name}: {out['error']}")
            items = [dict(it, provider=p.name) for it in (out.get("results") or [])]
            groups.append(items)
            counts[p.name] = len(items)
        merged = _interleave(groups, limit)
        return {
            "query": query,
            "count": len(merged),
            "results": merged,
            "providers": counts | ({"failed": failed} if failed else {}),
        }

    def providers_view(self) -> dict:
        """Где агент ищет: категории web/academic/video с провайдерами и их состоянием."""
        import os

        explicit = (getattr(self._settings, "search_provider", "") or "").lower()
        tavily = bool(os.environ.get("TAVILY_API_KEY"))
        serper = bool(os.environ.get("SERPER_API_KEY"))
        web: list[dict] = []
        if serper:
            web.append({"name": "serper", "enabled": True, "note": "ключ задан — первый в цепочке"})
        if tavily:
            web.append({"name": "tavily", "enabled": True, "note": "ключ задан"})
        web.extend(
            [
                {"name": "ddg", "enabled": True, "note": "без ключа (иногда анти-бот)"},
                {"name": "wikipedia", "enabled": True, "note": "без ключа"},
                {"name": "hackernews", "enabled": True, "note": "без ключа"},
            ]
        )
        if explicit and explicit not in ("chain", "arxiv"):
            # явный провайдер из настроек: цепочка не используется
            for w in web:
                w["enabled"] = w["name"] == explicit
        academic = [
            {"name": "arxiv", "enabled": True, "note": "без ключа — препринты"},
            {"name": "openalex", "enabled": True, "note": "без ключа — библиография всех работ"},
            {"name": "semantic_scholar", "enabled": True, "note": "без ключа — цитирования (лимит ~1 rps)"},
        ]
        video = [{"name": "youtube", "enabled": True, "note": "yt-dlp, без ключа; фолбэк — веб-поиск"}]
        return {
            "web": {
                "mode": "single" if explicit and explicit != "chain" else "chain",
                "providers": web,
            },
            "academic": {"mode": "aggregate", "providers": academic},
            "video": {"mode": "single", "providers": video},
        }

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
