"""REST «Сегодня»."""

from fastapi import APIRouter


def make_router(svc) -> APIRouter:
    """Роуты дашборда (B-005)."""
    r = APIRouter(prefix="/today", tags=["today"])

    @r.get("")
    def snapshot():
        """Снимок дня: сессия, курсы, чтение, повторения, входящие, источники."""
        return svc.snapshot()

    return r
