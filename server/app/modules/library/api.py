"""REST библиотеки: /api/sources, /api/jobs, /api/activities в learning."""

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from .schemas import ChapterCard, FromUrlCreate, FromUrlOut, JobOut, OutlineOut, SourceCard, SourceCreate


class ProcessOut(BaseModel):
    """Ответ запуска обработки."""

    ok: bool
    job_id: int | None = None


def make_router(svc, chat=None) -> APIRouter:
    """Роуты библиотеки; chat — get-or-create разговора главы (split-view, B-006)."""
    r = APIRouter(tags=["library"])

    @r.post("/sources", response_model=SourceCard)
    def create_source(body: SourceCreate) -> SourceCard:
        return _card(
            svc.add_source(body.kind, body.title, body.url, body.local_path, course_id=body.course_id)
        )

    @r.post("/sources/upload")
    async def upload_source(file: UploadFile = File(...), title: str | None = Form(None)) -> dict:
        data = await file.read()
        result = svc.upload_pdf(file.filename or "book.pdf", data, title)
        out = _card(result).model_dump()
        out["job_id"] = result.get("job_id")
        return out

    @r.post("/sources/from-url", response_model=FromUrlOut)
    def from_url(body: FromUrlCreate) -> FromUrlOut:
        """Скачать и добавить материал по ссылке (YouTube/PDF/статья); обработка — job."""
        return FromUrlOut(**svc.from_url(body.url))

    @r.get("/sources", response_model=list[SourceCard])
    def list_sources(
        kind: str | None = None, q: str | None = None, sort: str = "created"
    ) -> list[SourceCard]:
        del sort
        return [_card(s) for s in svc.list_sources(kind=kind, q=q)]

    @r.get("/sources/{ref}", response_model=None)
    def get_source(ref: str):
        return svc.get_source(ref)

    @r.post("/sources/{ref}/process", response_model=ProcessOut)
    def process(ref: str, force: bool = False) -> ProcessOut:
        result = svc.process_source(ref, force=force)
        return ProcessOut(ok=bool(result.get("ok")), job_id=result.get("job_id"))

    @r.delete("/sources/{ref}")
    def delete_source(ref: str):
        return svc.delete_source(ref)

    @r.get("/sources/{ref}/chapters", response_model=list[ChapterCard])
    def chapters(ref: str) -> list[ChapterCard]:
        return [ChapterCard(**ch) for ch in svc.list_chapters(ref)]

    @r.get("/sources/{ref}/file")
    def source_file(ref: str):
        """Оригинальный PDF источника — встроенный просмотрщик (inline, с Range)."""
        from fastapi.responses import FileResponse

        path = svc.source_file(ref)
        return FileResponse(
            path, media_type="application/pdf", filename=path.name, content_disposition_type="inline"
        )

    @r.get("/sources/{ref}/outline", response_model=OutlineOut)
    def outline(ref: str) -> OutlineOut:
        """Оглавление книги: стартовые страницы, номера глав, секции (из БД, для старых — матч закладок)."""
        return OutlineOut(**svc.chapter_pages(ref))

    @r.get("/sources/{ref}/images/{name}")
    def source_image(ref: str, name: str):
        """Картинка главы (рендер сплиттера) — только basename из images/ источника."""
        from fastapi.responses import FileResponse

        path = svc.source_image(ref, name)
        return FileResponse(path, media_type="image/png", content_disposition_type="inline")

    @r.get("/sources/{ref}/chapters/{idx}")
    def read_chapter(ref: str, idx: int, offset: int = 0, limit: int = 12000):
        return svc.read_chapter(ref, idx, offset, limit)

    @r.get("/sources/{ref}/segments")
    def segments(ref: str, from_s: float = 0, to_s: float | None = None):
        """Сегменты видео-транскрипта с таймкодами (B-006); from/to — окно в секундах."""
        data = svc.segments(ref)
        segs = [
            s
            for s in data["segments"]
            if (s["start"] >= from_s if from_s else True) and (s["start"] <= to_s if to_s else True)
        ]
        return {"segments": segs, "video_id": data["video_id"], "url": data["url"]}

    @r.post("/sources/{ref}/chapters/{idx}/conversation")
    def chapter_conversation(ref: str, idx: int):
        """Разговор главы (get-or-create, B-006): split-view продолжает тот же разговор."""
        return chat.chapter_conversation(ref, idx)

    @r.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: int) -> JobOut:
        return JobOut(**svc.get_job(job_id))

    def _card(s: dict) -> SourceCard:
        return SourceCard(
            id=s["id"],
            uid=s["uid"],
            kind=s["kind"],
            title=s["title"],
            author=s.get("author"),
            url=s.get("url"),
            status=s["status"],
            summary=s.get("summary"),
            meta=s.get("meta", {}),
            chapters_count=s.get("chapters_count", 0),
            last_error=s.get("last_error"),
        )

    return r
