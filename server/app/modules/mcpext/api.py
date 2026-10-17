"""REST mcpext: сторонние MCP-подключения (список, проверка, конструктор, CRUD)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field


class ProbeIn(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class DraftIn(BaseModel):
    brief: str = Field(min_length=3)


class CreateIn(BaseModel):
    name: str
    url: str
    description: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


def make_router(svc) -> APIRouter:
    """Роуты внешних MCP."""
    r = APIRouter(prefix="/mcpext", tags=["mcpext"])

    @r.get("")
    def list_all():
        return svc.list_mcps()

    @r.post("/probe")
    def probe(body: ProbeIn):
        return svc.probe(body.url, body.headers)

    @r.post("/draft")
    def draft(body: DraftIn):
        return svc.draft(body.brief)

    @r.post("")
    def create(body: CreateIn):
        return svc.create(body.name, body.url, body.description, body.headers)

    @r.post("/{name}/refresh")
    def refresh(name: str):
        return svc.refresh(name)

    @r.delete("/{name}")
    def delete(name: str):
        return svc.delete(name)

    return r
