"""REST библиотеки: /api/sources, /api/jobs, /api/activities в learning."""

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from .schemas import ChapterCard, JobOut, OutlineOut, SourceCard, SourceCreate


class ProcessOut(BaseModel):
    """Ответ запуска обработки."""

    ok: bool
    job_id: int | None = None


def make_router(svc) -> APIRouter:
    """Роуты библиотеки."""
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
        """Стартовые страницы PDF по главам (закладки, кэш до следующей обработки)."""
        return OutlineOut(**svc.chapter_pages(ref))

    @r.get("/sources/{ref}/chapters/{idx}")
    def read_chapter(ref: str, idx: int, offset: int = 0, limit: int = 12000):
        return svc.read_chapter(ref, idx, offset, limit)

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
        )

    return r
