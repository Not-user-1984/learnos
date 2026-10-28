"""Модуль ревизии: аудитор кода, задачи, ветки agent/* (T-038)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...kernel.module import Module
from .agents import register_agents
from .service import RevisionService
from .tools import revision_tools


class BranchIn(BaseModel):
    """Ветка агента для отклонения."""

    branch: str = Field(min_length=6)


class RevisionModule(Module):
    """Read-only ревизия репо + подготовка веток; применение — всегда за человеком."""

    name = "revision"

    def wire(self, c) -> None:
        c.revision = RevisionService(c.settings)
        register_agents(c)

    def routers(self, c) -> list[APIRouter]:
        r = APIRouter(prefix="/revision", tags=["revision"])

        @r.get("/branches")
        def branches():
            """Подготовленные агентом ветки (дневник data/git-branches)."""
            return c.revision.prepared_branches()

        @r.post("/branch/reject")
        def reject(body: BranchIn):
            """Удалить подготовленную ветку agent/* вместе с worktree."""
            return c.revision.reject_branch(body.branch)

        return [r]

    def tools(self, c) -> list:
        return revision_tools(c)
