"""REST обучения: активности и сессии (совместимые с v1 + новые)."""

from fastapi import APIRouter
from pydantic import BaseModel


class ActivityIn(BaseModel):
    """Создание активности."""

    source: str | int
    course_id: int | None = None


class SessionIn(BaseModel):
    """Создание сессии."""

    course_id: int | None = None
    activity: str | int | None = None
    chapter: int | None = None
    config: dict = {}


class AdvanceIn(BaseModel):
    """advance по-старому (v1)."""

    event: str
    payload: dict = {}


def make_router(svc) -> APIRouter:
    """Роуты обучения."""
    r = APIRouter(tags=["learning"])

    @r.post("/activities")
    def start_activity(body: ActivityIn):
        return svc.start_activity(body.source, body.course_id)

    @r.get("/activities")
    def list_activities(status: str | None = None):
        return svc.list_activities(status)

    @r.get("/activities/{ref}")
    def get_activity(ref: str):
        return svc.get_activity(ref)

    @r.post("/sessions")
    def start_session(body: SessionIn | None = None, course_id: int | None = None):
        if body is None:
            body = SessionIn(course_id=course_id)
        if body.course_id is None and course_id is not None:
            body.course_id = course_id
        return svc.start_session(
            course_id=body.course_id, activity_ref=body.activity, chapter_idx=body.chapter, config=body.config
        )

    @r.get("/sessions/{ref}")
    def get_session(ref):
        return svc.get_session_state(ref)

    @r.post("/sessions/{ref}/advance")
    def advance(ref: str, body: AdvanceIn):
        out = svc.advance(ref, body.event, body.payload)
        out.pop("_card", None)
        return out

    @r.post("/sessions/{ref}/finish")
    def finish(ref: str, block: dict | None = None):
        return svc.finish_session(ref, block)

    return r
