"""qBittorrent WebUI API v2: добавление торрентов и статус.

Аутентификация: WebUI API-key (Bearer, qBit >= 5.x) либо пара username/password
(login → cookie SID). Категория learnos-books — сигнал для hook'а LearnOS.
"""

import httpx

LEARNOS_BOOKS_CATEGORY = "learnos-books"


class QbitError(RuntimeError):
    """qBittorrent недоступен или отклонил запрос."""


class QbitClient:
    """Минимум: add / info / version."""

    def __init__(
        self,
        url: str,
        api_key: str = "",
        username: str = "",
        password: str = "",
        timeout: float = 15.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        if api_key:
            self._client.headers["Authorization"] = f"Bearer {api_key}"
        elif username:
            resp = self._client.post(
                f"{self._url}/api/v2/auth/login",
                data={"username": username, "password": password},
            )
            if resp.status_code != 200 or resp.text.strip() != "Ok.":
                raise QbitError("qbit login не прошёл")
        else:
            raise QbitError("qbit: нужен api_key или username/password")

    def close(self) -> None:
        self._client.close()

    def _check(self, resp: httpx.Response, what: str) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise QbitError(f"qbit {resp.status_code} на {what}: ключ/логин не принят")
        if resp.status_code != 200:
            raise QbitError(f"qbit {resp.status_code} на {what}")
        return resp

    def version(self) -> str:
        resp = self._check(self._client.get(f"{self._url}/api/v2/app/version"), "version")
        return resp.text.strip()

    def add(self, link: str, category: str = "") -> dict:
        """Добавить торрент (magnet / torrent-url); категория — метка для хуков.

        qBit отвечает 200 "Ok." на принятое и 202 на дубликат/флуд — оба
        означают, что раздача в клиенте.
        """
        data = {"urls": link}
        if category:
            data["category"] = category
        resp = self._client.post(f"{self._url}/api/v2/torrents/add", data=data)
        if resp.status_code in (401, 403):
            raise QbitError(f"qbit {resp.status_code} на torrents/add: ключ/логин не принят")
        if resp.status_code not in (200, 202):
            raise QbitError(f"qbit {resp.status_code} на torrents/add")
        if resp.status_code == 200 and resp.text.strip().lower() not in ("ok.", ""):
            raise QbitError(f"qbit add отклонён: {resp.text.strip()[:100]}")
        return {
            "added": True,
            "category": category or None,
            "link": link[:80],
            "duplicate": resp.status_code == 202,
        }

    def torrents(self, limit: int = 15) -> list[dict]:
        """Активные и завершённые раздачи с прогрессом."""
        resp = self._check(self._client.get(f"{self._url}/api/v2/torrents/info"), "torrents/info")
        rows = resp.json()
        rows.sort(key=lambda r: r.get("added_on", 0), reverse=True)
        out = []
        for r in rows[:limit]:
            out.append(
                {
                    "name": r.get("name", "?"),
                    "category": r.get("category", ""),
                    "progress": round(float(r.get("progress", 0)) * 100, 1),
                    "state": r.get("state", "?"),
                    "size": int(r.get("size", 0)),
                    "hash": r.get("hash", ""),
                }
            )
        return out
