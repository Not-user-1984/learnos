from fastapi import Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import core, skills_loader


class SourceIn(BaseModel):
    course_id: int
    kind: str
    title: str
    url: str | None = None
    local_path: str | None = None


class AdvanceIn(BaseModel):
    event: str
    payload: dict = {}


class CourseIn(BaseModel):
    topic: str
    plan: dict = {}


class SkillIn(BaseModel):
    kwargs: dict = {}


def make_router():
    from fastapi import APIRouter

    r = APIRouter(prefix="/api")

    @r.get("/", response_class=HTMLResponse)
    def index():
        return "<h1>learnos</h1><p>API: /api/*, MCP: /mcp</p>"

    @r.post("/courses")
    def courses_create(data: CourseIn):
        return core.create_course(data.topic, data.plan)

    @r.get("/courses")
    def courses_list():
        return core.list_courses()

    @r.post("/sources")
    def sources_add(data: SourceIn):
        return core.add_source(**data.model_dump())

    @r.get("/courses/{course_id}/sources")
    def sources_list(course_id: int):
        return core.list_sources(course_id)

    @r.post("/sources/{source_id}/process")
    def sources_process(source_id: int):
        return core.process_source(source_id)

    @r.get("/sources/{source_id}/chapters")
    def chapters_list(source_id: int):
        return core.list_chapters(source_id)

    @r.get("/sources/{source_id}/chapters/{chapter}")
    def chapters_read(source_id: int, chapter: int, offset: int = 0, limit: int = 12000):
        return core.read_chapter(source_id, chapter, offset, limit)

    @r.get("/search")
    def search(q: str, limit: int = 10):
        return core.search_chunks(q, limit)

    @r.post("/sessions")
    def sessions_start(course_id: int):
        return core.start_session(course_id)

    @r.get("/sessions/{session_id}")
    def sessions_get(session_id: int):
        return core.get_session(session_id)

    @r.post("/sessions/{session_id}/advance")
    def sessions_advance(session_id: int, data: AdvanceIn):
        return core.advance(session_id, data.event, data.payload)

    @r.post("/sessions/{session_id}/finish")
    def sessions_finish(session_id: int, block: dict = Body(...)):
        return core.finish_session(session_id, block)

    @r.get("/blocks")
    def blocks_list(course_id: int | None = None):
        return core.list_blocks(course_id)

    @r.get("/blocks/{block_uid}")
    def blocks_get(block_uid: str):
        return core.get_block(block_uid)

    @r.get("/skills")
    def skills_list():
        return skills_loader.registry_info()

    @r.post("/skills/{name}")
    def skills_run(name: str, data: SkillIn):
        return skills_loader.run_skill(name, data.kwargs)

    return r
