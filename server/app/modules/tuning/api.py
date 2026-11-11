"""REST tuning: промпты агентов, подтверждение правок, конструктор кастомных агентов."""

from dataclasses import asdict as _asdict

from fastapi import APIRouter
from pydantic import BaseModel, Field


class AgentDraftIn(BaseModel):
    """Пожелание для конструктора агентов."""

    brief: str = Field(min_length=3)


class AgentCreateIn(BaseModel):
    """Создание/обновление кастомного агента."""

    name: str
    description: str
    prompt: str
    tools: list[str] = Field(default_factory=list)


class CardMarkIn(BaseModel):
    """Пометка карточки в чате, из которой нажали кнопку (B-003): статус — в БД."""

    conversation_uid: str | None = None
    card_id: str | None = None


def make_router(svc, card_state=None) -> APIRouter:
    """Роуты настройки агентов; card_state — пометка карточек чата (B-003)."""

    def _mark(body: CardMarkIn | None, status: str) -> None:
        if card_state is not None and body is not None:
            card_state.mark(body.conversation_uid or "", body.card_id or "", status)

    r = APIRouter(prefix="/tuning", tags=["tuning"])

    @r.get("/prompts")
    def prompts():
        return [_asdict(p) for p in svc.list_prompts()]

    @r.get("/prompts/{agent}")
    def prompt(agent: str):
        return svc.read_prompt(agent)

    @r.get("/changes")
    def changes(status: str | None = None):
        return svc.changes(status)

    @r.post("/changes/{change_id}/approve")
    def approve(change_id: int, body: CardMarkIn | None = None):
        out = svc.apply_change(change_id)
        _mark(body, "applied")
        return out

    @r.post("/changes/{change_id}/reject")
    def reject(change_id: int, body: CardMarkIn | None = None):
        out = svc.reject_change(change_id)
        _mark(body, "rejected")
        return out

    @r.post("/prompts/{agent}/reset")
    def reset(agent: str):
        return svc.reset_prompt(agent)

    @r.post("/skills/{name}/reset")
    def reset_skill(name: str):
        """Снять override builtin-скилла — вернуть файлы из кода (бэкап перед снятием)."""
        return svc.reset_skill(name)

    # --- конструктор кастомных агентов ---

    @r.get("/tools")
    def tools():
        return svc.tools_catalog()

    @r.get("/agents")
    def custom_agents():
        return svc.custom_agents()

    @r.post("/agents/draft")
    def draft_agent(body: AgentDraftIn):
        return svc.draft_custom_agent(body.brief)

    @r.post("/agents")
    def create_agent(body: AgentCreateIn):
        return svc.create_custom_agent(body.name, body.description, body.prompt, body.tools)

    @r.patch("/agents/{name}")
    def update_agent(name: str, body: AgentCreateIn):
        del body.name
        return svc.update_custom_agent(name, body.description, body.prompt, body.tools)

    @r.delete("/agents/{name}")
    def delete_agent(name: str):
        return svc.delete_custom_agent(name)

    return r
