"""REST tuning: подтверждение/отклон правок промптов, сброс, история."""

from dataclasses import asdict as _asdict

from fastapi import APIRouter


def make_router(svc) -> APIRouter:
    """Роуты настройки агентов."""
    r = APIRouter(prefix="/tuning", tags=["tuning"])

    @r.get("/prompts")
    def prompts():
        return [_asdict(p) for p in svc.list_prompts()]

    @r.get("/changes")
    def changes(status: str | None = None):
        return svc.changes(status)

    @r.post("/changes/{change_id}/approve")
    def approve(change_id: int):
        return svc.apply_change(change_id)

    @r.post("/changes/{change_id}/reject")
    def reject(change_id: int):
        return svc.reject_change(change_id)

    @r.post("/prompts/{agent}/reset")
    def reset(agent: str):
        return svc.reset_prompt(agent)

    return r
