"""REST предложений (B-010)."""

from fastapi import APIRouter
from pydantic import BaseModel


class DecisionIn(BaseModel):
    decision: str  # accepted | rejected


def make_router(svc) -> APIRouter:
    r = APIRouter(prefix="/proposals", tags=["proposals"])

    @r.get("")
    def list_proposals():
        return svc.list()

    # ref:path — ветка содержит слэш (agent/fix-x), обычный сегмент даёт 404 (B-011)
    @r.post("/{kind}/{ref:path}/decide")
    def decide(kind: str, ref: str, body: DecisionIn):
        return svc.decide(kind, ref, body.decision)

    return r
