"""REST messenger: статус и тестовая отправка."""

from fastapi import APIRouter
from pydantic import BaseModel


class TestIn(BaseModel):
    """Тестовая отправка."""

    text: str = "Привет от LearnOS! Мост работает 🚀"


def make_router(svc) -> APIRouter:
    """Роуты messenger."""
    r = APIRouter(prefix="/messenger", tags=["messenger"])

    @r.get("/status")
    def status():
        return {"configured": svc.configured}

    @r.post("/test")
    def test_send(body: TestIn | None = None):
        result = svc.send_text((body or TestIn()).text)
        return result

    return r
