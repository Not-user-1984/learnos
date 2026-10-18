"""Настройки связи с внешним миром (UI → БД → живой Settings): поиск и прокси.

Ключи поиска (Tavily/Serper), socks5/http-прокси и vless-ключ (xray-sidecar делает
из него socks5://xray:1080 внутри стека). При применении обновляем поля Settings —
их читают httpx-клиенты поиска, yt-dlp и Telegram-мост.
"""

import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

log = logging.getLogger("learnos.research")

KEYS = ("search_provider", "search_api_key", "proxy_url", "vless_key")
XRAY_PROXY = "socks5://xray:1080"  # sidecar-сервис в docker-compose


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_connectivity(uow) -> dict:
    """Прочитать app_settings → словарь настроек связи."""
    import sqlalchemy as sa

    with uow() as session:
        rows = session.execute(sa.text("SELECT key, value FROM app_settings")).fetchall()
    return {k: "" for k in KEYS} | {r[0]: r[1] or "" for r in rows if r[0] in KEYS}


def save_connectivity(uow, patch: dict) -> dict:
    """Сохранить только известные ключи (пустое значение = сброс)."""
    import sqlalchemy as sa

    clean = {k: str(patch.get(k, "") or "").strip() for k in KEYS}
    with uow() as session:
        for k, v in clean.items():
            session.execute(
                sa.text(
                    "INSERT INTO app_settings (key, value, updated_at) VALUES (:k, :v, :t) "
                    "ON CONFLICT(key) DO UPDATE SET value=:v, updated_at=:t"
                ),
                {"k": k, "v": v, "t": _now()},
            )
    return clean


def effective_proxy(values: dict, current: str) -> str:
    """Прокси из настроек: vless → sidecar; иначе явный URL; иначе текущий (env)."""
    if values.get("vless_key"):
        return XRAY_PROXY
    p = values.get("proxy_url", "").strip()
    return p or current


def apply_to_settings(settings, values: dict) -> dict:
    """Применить настройки к живому Settings (поиск/веб/ютуб/телеграм)."""
    provider = values.get("search_provider", "").strip().lower()
    if provider in ("", "chain", "ddg", "wikipedia", "hackernews", "arxiv", "tavily", "serper"):
        settings.search_provider = provider or "chain"
    api_key = values.get("search_api_key", "").strip()
    if api_key:
        import os

        if settings.search_provider == "tavily":
            os.environ["TAVILY_API_KEY"] = api_key
        elif settings.search_provider == "serper":
            os.environ["SERPER_API_KEY"] = api_key
        else:
            os.environ["TAVILY_API_KEY"] = api_key  # автоопределение по типу не критично
    proxy = effective_proxy(values, settings.web_proxy)
    settings.web_proxy = proxy
    settings.yt_proxy = proxy
    if proxy:
        settings.telegram_proxy = proxy
    return {"provider": settings.search_provider, "proxy": proxy, "vless": bool(values.get("vless_key"))}


# --- vless → xray config ---

_VLESS = re.compile(r"^vless://([0-9a-fA-F-]{36})@([^:/?#]+):(\d+)")


def vless_to_config(link: str) -> dict:
    """vless://uuid@host:port?params#name → конфиг xray-core (inbound socks:1080)."""
    m = _VLESS.match(link.strip())
    if not m:
        raise ValueError("не похоже на vless-ссылку (vless://uuid@host:порт?…)")
    uuid_, host, port = m.group(1), m.group(2), int(m.group(3))
    q = {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}
    flow = q.get("flow", "")
    network = q.get("type", "tcp")
    security = q.get("security", "none")

    stream: dict = {"network": network}
    if network == "ws":
        stream["wsSettings"] = {"path": unquote(q.get("path", "/")), "headers": {"Host": q.get("host", host)}}
    if network == "grpc":
        stream["grpcSettings"] = {"serviceName": q.get("serviceName", "")}
    if security == "tls":
        stream["security"] = "tls"
        stream["tlsSettings"] = {
            "serverName": q.get("sni", host),
            "allowInsecure": q.get("allowInsecure", "0") == "1",
            "fingerprint": q.get("fp", "chrome"),
        }
    elif security == "reality":
        stream["security"] = "reality"
        stream["realitySettings"] = {
            "serverName": q.get("sni", host),
            "fingerprint": q.get("fp", "chrome"),
            "publicKey": q.get("pbk", ""),
            "shortId": q.get("sid", ""),
            "spiderX": q.get("spx", ""),
        }

    user: dict = {"id": uuid_, "encryption": q.get("encryption", "none")}
    if flow:
        user["flow"] = flow

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks",
                "port": 1080,
                "listen": "0.0.0.0",
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
                "streamSettings": stream,
            },
            {"tag": "direct", "protocol": "freedom"},
        ],
        "routing": {"rules": [{"type": "field", "outboundTag": "proxy"}]},
    }


def write_xray_config(link: str, data_dir) -> str:
    """Валидировать vless и записать конфиг для sidecar-а (он подхватит за ~15с)."""
    config = vless_to_config(link)
    xray_dir = data_dir / "xray"
    xray_dir.mkdir(parents=True, exist_ok=True)
    path = xray_dir / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def masked(values: dict) -> dict:
    """Вид для UI: ключи маскируются."""

    def _m(v: str) -> str:
        return (v[:6] + "…" + v[-4:]) if len(v) > 14 else ("задан" if v else "")

    return {
        "search_provider": values.get("search_provider", ""),
        "search_api_key": _m(values.get("search_api_key", "")),
        "proxy_url": values.get("proxy_url", ""),
        "vless_key": _m(values.get("vless_key", "")),
        "has_search_api_key": bool(values.get("search_api_key")),
        "has_vless_key": bool(values.get("vless_key")),
    }
