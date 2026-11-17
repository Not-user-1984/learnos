"""REST повторений: очередь и сводка (ответ — через агента-экзаменатора в чате)."""

from fastapi import APIRouter
from pydantic import BaseModel


class AnswerCardIn(BaseModel):
    """Оценка карточки-суть кнопкой, без LLM (B-014)."""

    block_uid: str
    card_id: str
    grade: str  # again | hard | good


def make_router(svc) -> APIRouter:
    """Роуты повторений (B-004/B-014)."""
    r = APIRouter(prefix="/review", tags=["review"])

    @r.get("/queue")
    def queue(limit: int = 5, source: str | None = None):
        """Очередь повторений на сегодня (сначала слабые, затем созревшие);
        source — набор по книге (B-014)."""
        return svc.queue(limit, source=source)

    @r.get("/stats")
    def stats(source: str | None = None):
        """Сводка: due_today / overdue / total — для дашборда и бейджа."""
        return svc.stats(source=source)

    @r.post("/answer-card")
    def answer_card(body: AnswerCardIn):
        """Оценить карточку: «Не помню» / «Трудно» / «Помню» → SM-2 (B-014)."""
        return svc.answer_card(body.block_uid, body.card_id, body.grade)

    return r
