"""Веб-статья как источник: _run_web раскладывает главы research.extract_chapters."""

from pathlib import Path
from types import SimpleNamespace

from app.kernel.clock import SystemClock
from app.modules.library.service import LibraryService


class FakeUow:
    session = None

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


class FakeSources:
    def __init__(self) -> None:
        self.row = {"id": 7, "uid": "src_w", "title": "https://example.com/x", "kind": "web"}
        self.updates: list[dict] = []

    def update(self, session, source_id, **values) -> None:
        del session, source_id
        self.row.update(values)
        self.updates.append(values)


class FakeChapters:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    def insert(self, session, **values) -> int:
        del session
        self.inserted.append(values)
        return len(self.inserted)


class FakeResearch:
    def extract_chapters(self, url: str, max_chapters: int = 30) -> dict:
        del url, max_chapters
        return {
            "title": "Гайд по observability",
            "chapters": [
                {"title": "Логи", "text": "про логы " * 100},
                {"title": "Метрики", "text": "про метрики " * 100},
            ],
        }


def make_service(tmp_path: Path) -> tuple[LibraryService, FakeSources, FakeChapters]:
    sources, chapters = FakeSources(), FakeChapters()
    svc = LibraryService(
        uow=lambda: FakeUow(),
        sources=sources,  # type: ignore[arg-type]
        chapters=chapters,  # type: ignore[arg-type]
        jobs=SimpleNamespace(),  # type: ignore[arg-type]
        skills=SimpleNamespace(),
        ids=SimpleNamespace(),
        clock=SystemClock(),
        settings=SimpleNamespace(data_dir=str(tmp_path)),
        research=FakeResearch(),
    )
    return svc, sources, chapters


def test_run_web_creates_chapters_and_title(tmp_path):
    svc, sources, chapters = make_service(tmp_path)
    result = svc._processing_uc._run_web(sources.row, "https://example.com/x")  # noqa: SLF001
    assert result["ok"] and result["chapters"] == 2 and result["title"] == "Гайд по observability"
    assert [c["idx"] for c in chapters.inserted] == [1, 2]
    first = chapters.inserted[0]
    assert Path(first["path"]).exists() and Path(first["path"]).read_text(encoding="utf-8").startswith(
        "# Логи"
    )
    assert sources.row["status"] == "processed"
    assert sources.row["title"] == "Гайд по observability"


def test_run_web_without_research_reports_error(tmp_path):
    sources = FakeSources()
    svc = LibraryService(
        uow=lambda: FakeUow(),
        sources=sources,  # type: ignore[arg-type]
        chapters=FakeChapters(),  # type: ignore[arg-type]
        jobs=SimpleNamespace(),  # type: ignore[arg-type]
        skills=SimpleNamespace(),
        ids=SimpleNamespace(),
        clock=SystemClock(),
        settings=SimpleNamespace(data_dir=str(tmp_path)),
        research=None,
    )
    result = svc._processing_uc._run_web(sources.row, "https://x")  # noqa: SLF001
    assert "error" in result
