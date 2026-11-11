"""Модуль ревизии: аудитор кода, задачи, ветки agent/* (T-038)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...kernel.module import Module
from .agents import register_agents
from .service import RevisionService
from .tools import revision_tools


class BranchIn(BaseModel):
    """Ветка агента для отклонения; conversation_uid+card_id — пометить карточку (B-003)."""

    branch: str = Field(min_length=6)
    conversation_uid: str | None = None
    card_id: str | None = None


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
            out = c.revision.reject_branch(body.branch)
            # карточка git_change в чате помечается отклонённой (B-003)
            card_state = getattr(c, "chat_cards", None)
            if card_state is not None:
                card_state.mark(body.conversation_uid or "", body.card_id or "", "rejected")
            return out

        return [r]

    def tools(self, c) -> list:
        return revision_tools(c)
