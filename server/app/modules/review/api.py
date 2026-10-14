"""REST повторений."""

from fastapi import APIRouter
from pydantic import BaseModel


class AnswerIn(BaseModel):
    """Ответ на вопрос повторения."""

    block_uid: str
    answer: str


def make_router(svc) -> APIRouter:
    """Роуты повторений."""
    r = APIRouter(prefix="/review", tags=["review"])

    @r.get("/queue")
    def queue(limit: int = 2):
        return svc.queue(limit)

    @r.post("/ask")
    def ask(block_uid: str | None = None):
        q = svc.ask(block_uid)
        return {
            "block_uid": q.block_uid,
            "title": q.title,
            "question": q.question,
            "message_id": q.message_id,
        }

    @r.post("/answer")
    def answer(body: AnswerIn):
        return svc.answer(body.block_uid, body.answer)

    return r
