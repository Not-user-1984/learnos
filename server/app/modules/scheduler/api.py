"""REST планировщика (B-010)."""

from fastapi import APIRouter
from pydantic import BaseModel


class EnabledIn(BaseModel):
    enabled: bool


def make_router(svc) -> APIRouter:
    r = APIRouter(prefix="/schedules", tags=["scheduler"])

    @r.get("")
    def list_schedules():
        return svc.list()

    @r.post("/{name}/enable")
    def enable(name: str, body: EnabledIn):
        return svc.set_enabled(name, body.enabled)

    @r.post("/{name}/run")
    def run_now(name: str):
        return svc.run_now(name)

    return r
