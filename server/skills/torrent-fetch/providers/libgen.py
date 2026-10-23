"""libgen: best-effort лейн прямых ссылок на книги (быстрее торрентов).

Два формата зеркал: libgen.li (search через /index.php, скачивание через
одноразовую ссылку get.php с ключом из /ads.php) и libgen.is (search.php +
dl.php). Зеркала падают часто — таймауты короткие, фейл лейна не ошибка:
вызывающий код просто уходит в торренты.
"""

import re
from pathlib import Path

import httpx

MIRRORS = ["https://libgen.li", "https://libgen.is"]
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_EXTS = ("pdf", "epub", "mobi", "azw3", "djvu", "fb2")


class LibgenError(RuntimeError):
    """libgen-лейн недоступен (зеркала легли / нужен прокси)."""


def _client(proxy: str = "", timeout: float = 25.0) -> httpx.Client:
    return httpx.Client(headers=_UA, timeout=timeout, follow_redirects=True, proxy=proxy or None)


class LibgenClient:
    """Поиск книг + прямое скачивание по md5."""

    def __init__(self, mirrors: list[str] | None = None, proxy: str = "") -> None:
        self._mirrors = mirrors or MIRRORS
        self._proxy = proxy

    # ── низкоуровневые хелперы ──────────────────────────────────────

    def _get(self, url: str, params: dict | None = None, referer: str = "") -> httpx.Response:
        headers = {"Referer": referer} if referer else {}
        try:
            with _client(self._proxy) as c:
                resp = c.get(url, params=params, headers=headers)
        except httpx.HTTPError as e:
            raise LibgenError(f"сеть: {e}") from e
        if resp.status_code != 200 or not resp.text:
            raise LibgenError(f"{url.split('/')[2]} → HTTP {resp.status_code}")
        return resp

    def _first_alive(self, path: str, params: dict) -> tuple[str, httpx.Response]:
        """Первое зеркало, ответившее 200."""
        last: Exception | None = None
        for mirror in self._mirrors:
            try:
                return mirror, self._get(f"{mirror}{path}", params)
            except LibgenError as e:
                last = e
        raise LibgenError(f"все зеркала недоступны: {last}")

    # ── поиск ───────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Найти книги: title/ext/size/md5, приоритет PDF."""
        rows = self._search_rows(query)
        found: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            md5 = row.get("md5", "")
            if not md5 or md5 in seen:
                continue
            if row.get("ext") and row["ext"] not in _EXTS:
                continue
            seen.add(md5)
            found.append(
                {
                    "kind": "libgen",
                    "title": f"{row['title']} [{row.get('ext') or '?'}]"[:120],
                    "indexer": f"libgen {row.get('author', '')}"[:40],
                    "size": row.get("size", 0),
                    "seeders": 0,
                    "md5": md5,
                    "ext": row.get("ext", ""),
                    "link": md5,
                }
            )
            if len(found) >= limit:
                break
        # PDF приоритетнее, внутри — по размеру (полное издание, не фрагмент)
        found.sort(key=lambda c: (c["ext"] != "pdf", -c["size"]))
        return found

    def _search_rows(self, query: str) -> list[dict]:
        """Поиск по всем зеркалам, первый живой формат."""
        # формат libgen.li: /index.php, md5 в ссылках ads.php
        try:
            mirror, resp = self._first_alive("/index.php", {"req": query, "res": 25, "column": "title"})
            rows = self._parse_li(resp.text)
            if rows:
                return rows
        except LibgenError:
            pass
        # формат libgen.is: /search.php
        mirror, resp = self._first_alive("/search.php", {"req": query, "res": 25, "column": "title"})
        del mirror
        return self._parse_is(resp.text)

    def _parse_li(self, html: str) -> list[dict]:
        """Строки libgen.li: md5 из ads.php, title из edition.php, cells после."""
        out = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            md5_m = re.search(r"ads\.php\?md5=([a-f0-9]{32})", row)
            title_m = re.search(r'edition\.php\?id=\d+"[^>]*>(.*?)</a>', row, re.S)
            if not md5_m or not title_m:
                continue
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
            # cells: [title-мусор, автор, издатель, год, язык, страницы, размер, формат]
            out.append(
                {
                    "md5": md5_m.group(1),
                    "title": title,
                    "author": cells[1] if len(cells) > 1 else "",
                    "ext": (cells[7] if len(cells) > 7 else "").lower().strip(),
                    "size": _size_bytes(cells[6] if len(cells) > 6 else ""),
                }
            )
        return out

    def _parse_is(self, html: str) -> list[dict]:
        """Строки libgen.is: md5 в href книги; cells: автор, название, год, размер, формат."""
        out = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            md5_m = re.search(r'md5=([a-f0-9]{32})"[^>]*>(.*?)</a>', row, re.S)
            if not md5_m:
                continue
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", md5_m.group(2))).strip()
            out.append(
                {
                    "md5": md5_m.group(1),
                    "title": title,
                    "author": cells[0] if cells else "",
                    "ext": (cells[7] if len(cells) > 7 else "").lower().strip(),
                    "size": _size_bytes(cells[6] if len(cells) > 6 else ""),
                }
            )
        return out

    # ── скачивание ──────────────────────────────────────────────────

    def download(self, md5: str, dest_dir: Path, filename_hint: str = "") -> Path:
        """Скачать файл по md5 в dest_dir; возвращает путь."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        last_err: Exception | None = None
        for mirror in self._mirrors:
            try:
                path = self._download_mirror(mirror, md5, dest_dir, filename_hint)
                if path is not None:
                    return path
            except httpx.HTTPError as e:
                last_err = e
        raise LibgenError(f"libgen download не удался: {last_err or 'файл недоступен на зеркалах'}")

    def _download_mirror(self, mirror: str, md5: str, dest_dir: Path, filename_hint: str) -> Path | None:
        """Попытка одного зеркала; None → попробовать следующее."""
        name = filename_hint or md5
        if not any(f".{e}" in name.lower() for e in _EXTS):
            name = f"{name}.pdf"
        safe = re.sub(r"[/\\?%*:|\"<>]", "_", name)[:120]
        path = dest_dir / safe

        # libgen.li: одноразовая ссылка get.php?..&key=.. со страницы ads.php;
        # ключ привязан к сессии — ads.php и скачивание в одном клиенте
        referer = f"{mirror}/ads.php?md5={md5}"
        try:
            with _client(self._proxy, timeout=25.0) as c:
                resp = c.get(f"{mirror}/ads.php", params={"md5": md5})
                if resp.status_code == 200:
                    m = re.search(
                        r'href="(get\.php\?md5=[a-f0-9]{32}(?:&amp;|&)key=[A-Z0-9]+)"',
                        resp.text,
                    )
                    if m:
                        one_time = f"{mirror}/{m.group(1).replace('&amp;', '&')}"
                        with c.stream("GET", one_time, headers={"Referer": referer}) as s:
                            if s.status_code == 200 and "text/html" not in s.headers.get("content-type", ""):
                                with open(path, "wb") as f:
                                    for chunk in s.iter_bytes(65536):
                                        f.write(chunk)
                                if path.stat().st_size >= 1024:
                                    return path
                                path.unlink(missing_ok=True)
        except httpx.HTTPError:
            pass
        # dl.php-путь (libgen.is-формат) отдельным клиентом
        dl_url = f"{mirror}/dl.php?md5={md5}"
        try:
            with _client(self._proxy, timeout=180.0) as c:
                with c.stream("GET", dl_url, headers={"Referer": referer}) as resp:
                    if resp.status_code == 200 and "text/html" not in resp.headers.get("content-type", ""):
                        with open(path, "wb") as f:
                            for chunk in resp.iter_bytes(65536):
                                f.write(chunk)
                        if path.stat().st_size >= 1024:
                            return path
                        path.unlink(missing_ok=True)
        except httpx.HTTPError:
            pass
        return None


def _size_bytes(s: str) -> int:
    """'12 [34] Kb' / '1.5 Mb' / '5 MB' → байты."""
    m = re.search(r"([\d.]+)(?:\s*\[[^\]]*\])?\s*(Kb|Mb|Gb|KB|MB|GB)?", s or "", re.I)
    if not m:
        return 0
    num = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "Kb").lower()
    mult = {"kb": 1000, "mb": 1_000_000, "gb": 1_000_000_000}[unit]
    return int(num * mult)
