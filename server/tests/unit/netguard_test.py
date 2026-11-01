"""R-08: netguard — SSRF-защита общая для web_read / from_url / _probe_pdf."""

import pytest

from app.kernel.errors import ValidationFailed
from app.kernel.netguard import assert_public_http_url, checked_get


def test_private_hosts_and_ips_rejected():
    for url in (
        "http://localhost:8765/api/health",
        "http://127.0.0.1:8006/",
        "http://192.168.0.105:8006/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]:8765/",
        "http://router.local/admin",
        "ftp://example.com/file",
    ):
        with pytest.raises(ValidationFailed):
            assert_public_http_url(url)


def test_allow_private_flag_disables_guard():
    assert_public_http_url("http://192.168.0.105:8006/", allow_private=True)  # не бросает


def test_checked_get_verifies_each_redirect_hop(monkeypatch):
    """Редирект с публичного хоста на приватный — отказ до соединения (R-08)."""
    from app.kernel import netguard

    class _Resp:
        def __init__(self, status: int, location: str | None = None):
            self.status_code = status
            self.headers = {"location": location} if location else {}

    class _Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url: str, headers=None):
            assert url == "https://public.example.com/start", url
            return _Resp(302, "http://127.0.0.1:8006/admin")

    monkeypatch.setattr(netguard.httpx, "Client", _Client)
    with pytest.raises(ValidationFailed):
        checked_get("https://public.example.com/start")


def test_checked_get_follows_public_redirects(monkeypatch):
    from app.kernel import netguard

    class _Resp:
        def __init__(self, status: int, location: str | None = None, text: str = ""):
            self.status_code = status
            self.headers = {"location": location} if location else {}
            self.text = text

    seen: list[str] = []

    class _Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url: str, headers=None):
            seen.append(url)
            if url.endswith("/start"):
                return _Resp(301, "https://example.org/final")
            return _Resp(200, text="ок")

    monkeypatch.setattr(netguard.httpx, "Client", _Client)
    r = checked_get("https://example.com/start")
    assert r.status_code == 200
    assert seen == ["https://example.com/start", "https://example.org/final"]
