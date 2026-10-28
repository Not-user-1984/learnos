"""POST /api/sources/from-url: YouTube/PDF/статья по ссылке одним действием."""

from __future__ import annotations

import functools
import io
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import fitz
import pytest


def _make_pdf() -> bytes:
    """Маленькая книга: 2 страницы с закладками (как в test_source_file)."""
    doc = fitz.open()
    for i, name in enumerate(("Глава A", "Глава B"), start=1):
        page = doc.new_page()
        page.insert_text((72, 96), f"{name} — страница {i}")
    doc.set_toc([[1, "Глава A", 1], [1, "Глава B", 2]])
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


class _QuietHandler(SimpleHTTPRequestHandler):
    """Файловый сервер без логов в stderr тестов."""

    def log_message(self, *args) -> None:  # noqa: N802 — имя из http.server
        del args


@pytest.fixture
def http_dir(tmp_path):
    """Локальный http-сервер на свободном порту: (base_url, каталог файлов)."""
    root = tmp_path / "www"
    root.mkdir()
    pdf = _make_pdf()
    (root / "book.pdf").write_bytes(pdf)
    (root / "noext").write_bytes(pdf)  # без расширения → content-type octet-stream, ловим magic-байтами
    (root / "article.html").write_text(
        "<html><title>Статья</title><body><h1>Раз</h1><p>текст статьи достаточной длины</p></body></html>",
        encoding="utf-8",
    )
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", root, pdf
    server.shutdown()
    thread.join()


def test_from_url_youtube_creates_video_source(client):
    r = client.post(
        "/api/sources/from-url",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["uid"].startswith("src_")
    assert body["kind"] == "video"
    assert body["processing"] is True
    assert isinstance(body["job_id"], int)

    src = client.get(f"/api/sources/{body['uid']}").json()
    assert src["kind"] == "video"
    assert src["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_from_url_pdf_downloads_book(client, http_dir, container):
    base, _root, pdf = http_dir
    r = client.post("/api/sources/from-url", json={"url": f"{base}/book.pdf"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "book"
    assert body["title"] == "book"
    assert isinstance(body["job_id"], int)

    src = client.get(f"/api/sources/{body['uid']}").json()
    assert src["kind"] == "book"
    assert src["local_path"]
    from pathlib import Path

    assert Path(src["local_path"]).read_bytes() == pdf


def test_from_url_pdf_by_magic_bytes_without_extension(client, http_dir):
    """Трекерная ссылка без .pdf и с octet-stream: книгу ловим по %PDF- в ответе."""
    base, _root, _pdf = http_dir
    r = client.post("/api/sources/from-url", json={"url": f"{base}/noext"})
    assert r.status_code == 200
    assert r.json()["kind"] == "book"


def test_from_url_web_article(client, http_dir):
    base, _root, _pdf = http_dir
    r = client.post("/api/sources/from-url", json={"url": f"{base}/article.html"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "web"
    assert body["uid"].startswith("src_")
    src = client.get(f"/api/sources/{body['uid']}").json()
    assert src["kind"] == "web"


def test_from_url_size_limit(client, http_dir, monkeypatch):
    from app.modules.library import service as lib_service

    monkeypatch.setattr(lib_service, "MAX_URL_PDF_BYTES", 64)
    base, _root, _pdf = http_dir
    r = client.post("/api/sources/from-url", json={"url": f"{base}/book.pdf"})
    assert r.status_code == 422
    assert "лимит" in r.json()["message"] or "МБ" in r.json()["message"]


def test_from_url_broken_url_is_readable(client):
    r = client.post("/api/sources/from-url", json={"url": "http://127.0.0.1:1/book.pdf"})
    assert r.status_code == 502
    assert "не удалось скачать" in r.json()["message"]


def test_from_url_rejects_non_http(client):
    r = client.post("/api/sources/from-url", json={"url": "ftp://example.com/book.pdf"})
    assert r.status_code == 422
    assert "http(s)" in r.json()["message"]


def test_from_url_youtube_host_variants(client):
    for url in ("https://youtu.be/dQw4w9WgXcQ", "https://youtube.com/shorts/abc12345678"):
        r = client.post("/api/sources/from-url", json={"url": url})
        assert r.status_code == 200
        assert r.json()["kind"] == "video"
