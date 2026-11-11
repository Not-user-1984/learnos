"""Видео-источник: обработка сохраняет настоящий тайтл и кладёт транскрипт одной записью."""

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


class FakeUowFactory:
    """UoW без БД: session не используется фейковыми репозиториями."""

    def __call__(self) -> FakeUow:
        return FakeUow()


class FakeSources:
    def __init__(self, row: dict) -> None:
        self.row = dict(row)
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


def make_service(
    tmp_path: Path, *, skill_title: str, source_title: str
) -> tuple[LibraryService, FakeSources, FakeChapters]:
    transcript = tmp_path / "video.md"
    transcript.write_text("# заголовок\n\nтранскрипт", encoding="utf-8")
    skills = SimpleNamespace(
        run=lambda name, payload: {
            "ok": True,
            "title": skill_title,
            "path": str(transcript),
            "video_id": "abc123",
            "lang": "ru",
            "preview": "первые строки",
        }
    )
    sources = FakeSources({"id": 1, "uid": "src_x", "title": source_title, "kind": "video"})
    chapters = FakeChapters()
    svc = LibraryService(
        uow=FakeUowFactory(),
        sources=sources,  # type: ignore[arg-type]
        chapters=chapters,  # type: ignore[arg-type]
        jobs=SimpleNamespace(),  # type: ignore[arg-type]
        skills=skills,
        ids=SimpleNamespace(),
        clock=SystemClock(),
        settings=SimpleNamespace(data_dir=str(tmp_path)),
    )
    return svc, sources, chapters


def test_run_video_saves_real_title_over_url(tmp_path):
    svc, sources, _ = make_service(
        tmp_path, skill_title="Логирование в Python", source_title="https://youtu.be/abc123"
    )
    result = svc._processing_uc._run_video(sources.row, "https://youtu.be/abc123")
    assert result["ok"]
    assert sources.row["title"] == "Логирование в Python"
    assert sources.row["status"] == "processed"


def test_run_video_keeps_existing_title_when_skill_silent(tmp_path):
    svc, sources, _ = make_service(tmp_path, skill_title="", source_title="Конец эпохи кодеров")
    svc._processing_uc._run_video(sources.row, "https://youtu.be/abc123")
    assert sources.row["title"] == "Конец эпохи кодеров"


def test_run_video_single_chapter_with_transcript(tmp_path):
    svc, _, chapters = make_service(tmp_path, skill_title="Тайтл", source_title="url")
    svc._processing_uc._run_video({"id": 1, "uid": "src_x", "title": "url", "kind": "video"}, "url")
    assert len(chapters.inserted) == 1
    ch = chapters.inserted[0]
    assert ch["idx"] == 1
    assert ch["title"] == "Тайтл"
