"""Prowlarr: единый поиск по всем подключённым трекерам."""

import httpx

# категории *arr: 7000 books, 2000 movies, 3000 music, 5000 tv
CATEGORIES = {"books": 7000, "movies": 2000, "music": 3000, "tv": 5000}


class ProwlarrError(RuntimeError):
    """Prowlarr недоступен или отклонил запрос."""


class ProwlarrClient:
    """Тонкая обёртка над GET /api/v1/search."""

    def __init__(self, url: str, api_key: str, timeout: float = 20.0) -> None:
        self._url = url.rstrip("/")
        self._headers = {"X-Api-Key": api_key}
        self._timeout = timeout

    def search(self, query: str, cat: str = "books", limit: int = 20) -> list[dict]:
        """Найти раздачи; возвращает нормализованные кандидаты-торренты."""
        params: dict = {"query": query, "limit": limit}
        if cat in CATEGORIES:
            params["categories"] = CATEGORIES[cat]
        try:
            resp = httpx.get(
                f"{self._url}/api/v1/search", params=params, headers=self._headers, timeout=self._timeout
            )
        except httpx.HTTPError as e:
            raise ProwlarrError(f"prowlarr недоступен: {e}") from e
        if resp.status_code == 401:
            raise ProwlarrError("prowlarr 401: неверный api_key")
        if resp.status_code != 200:
            raise ProwlarrError(f"prowlarr {resp.status_code}")
        rows = resp.json()
        candidates = []
        for r in rows:
            if not r.get("seeders") and not r.get("magnetUrl"):
                continue
            candidates.append(
                {
                    "kind": "torrent",
                    "title": (r.get("title") or "")[:120],
                    "indexer": r.get("indexer", "?"),
                    "size": int(r.get("size") or 0),
                    "seeders": int(r.get("seeders") or 0),
                    "leechers": int(r.get("leechers") or 0),
                    "info_hash": r.get("infoHash") or "",
                    "link": r.get("downloadUrl") or r.get("magnetUrl") or "",
                    "categories": [c.get("name", "") for c in r.get("categories") or []],
                    "publish_date": r.get("publishDate") or "",
                }
            )
        # стабильно: сиды по убыванию
        candidates.sort(key=lambda c: c["seeders"], reverse=True)
        return candidates[:limit]
