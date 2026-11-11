"""REST повторений: очередь и сводка (ответ — через агента-экзаменатора в чате)."""

from fastapi import APIRouter


def make_router(svc) -> APIRouter:
    """Роуты повторений (B-004)."""
    r = APIRouter(prefix="/review", tags=["review"])

    @r.get("/queue")
    def queue(limit: int = 5):
        """Очередь повторений на сегодня (сначала слабые, затем созревшие)."""
        return svc.queue(limit)

    @r.get("/stats")
    def stats():
        """Сводка: due_today / overdue / total — для дашборда и бейджа."""
        return svc.stats()

    return r
