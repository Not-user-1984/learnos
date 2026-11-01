"""SSRF-защита: публичность URL и загрузка с проверкой каждого редиректа.

Единая точка для web_read / from_url / _probe_pdf / _run_web: раньше проверялся
только from_url, а research._fetch ходил куда угодно (loopback, LAN, metadata)
и следовал редиректам без проверок (R-08 аудита).
"""

import ipaddress
import socket
from contextlib import AbstractContextManager
from urllib.parse import urljoin, urlsplit

import httpx

from .errors import ValidationFailed

_PRIVATE_SUFFIXES = (".local", ".internal", ".lan", ".home.arpa")
_REDIRECTS = (301, 302, 303, 307, 308)


def assert_public_http_url(url: str, *, allow_private: bool = False) -> None:
    """http(s)-URL должен резолвиться только в публичные адреса (все A/AAAA).

    Raises:
        ValidationFailed: не http(s), внутреннее имя или приватный/зарезервированный IP.
    """
    if allow_private:
        return
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValidationFailed("нужна http(s)-ссылка")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith(_PRIVATE_SUFFIXES):
        raise ValidationFailed("внутренние адреса недоступны для загрузки по ссылке")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return  # не резолвится локально (прокси решит сам); соединение скажет своё
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValidationFailed("внутренние адреса недоступны для загрузки по ссылке")


def checked_get(
    url: str,
    *,
    allow_private: bool = False,
    proxy: str | None = None,
    timeout: httpx.Timeout | float = 25,
    headers: dict | None = None,
    max_redirects: int = 5,
) -> httpx.Response:
    """GET с ручным обходом редиректов — каждый hop проверен на публичность (R-08)."""
    current = url
    for _ in range(max_redirects + 1):
        assert_public_http_url(current, allow_private=allow_private)
        with httpx.Client(proxy=proxy, timeout=timeout, follow_redirects=False) as client:
            r = client.get(current, headers=headers or {})
        if r.status_code in _REDIRECTS and r.headers.get("location"):
            current = urljoin(current, r.headers["location"])
            continue
        return r
    raise ValidationFailed("слишком много переадресаций")


def checked_stream(
    url: str,
    *,
    allow_private: bool = False,
    proxy: str | None = None,
    timeout: httpx.Timeout | float = 25,
    headers: dict | None = None,
    max_redirects: int = 5,
) -> AbstractContextManager[httpx.Response]:
    """Stream-GET на финальный ответ: редиректы проверены, тело не качается дважды."""
    return _CheckedStream(
        url,
        allow_private=allow_private,
        proxy=proxy,
        timeout=timeout,
        headers=headers,
        max_redirects=max_redirects,
    )


class _CheckedStream:
    """Контекстный менеджер: идёт по редиректам (проверяя hops), отдаёт финальный stream."""

    def __init__(
        self,
        url: str,
        *,
        allow_private: bool,
        proxy: str | None,
        timeout: httpx.Timeout | float,
        headers: dict | None,
        max_redirects: int,
    ) -> None:
        self._url = url
        self._allow_private = allow_private
        self._proxy = proxy
        self._timeout = timeout
        self._headers = headers
        self._max_redirects = max_redirects
        self._cm: AbstractContextManager[httpx.Response] | None = None

    def __enter__(self) -> httpx.Response:
        current = self._url
        for _ in range(self._max_redirects + 1):
            assert_public_http_url(current, allow_private=self._allow_private)
            cm = httpx.stream(
                "GET",
                current,
                headers=self._headers or {},
                timeout=self._timeout,
                follow_redirects=False,
                proxy=self._proxy,
            )
            response = cm.__enter__()
            if response.status_code in _REDIRECTS and response.headers.get("location"):
                cm.__exit__(None, None, None)
                current = urljoin(current, response.headers["location"])
                continue
            self._cm = cm
            return response
        raise ValidationFailed("слишком много переадресаций")

    def __exit__(self, *exc) -> None:
        if self._cm is not None:
            self._cm.__exit__(*exc)
            self._cm = None
