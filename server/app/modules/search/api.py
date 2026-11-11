"""REST поиска."""

from fastapi import APIRouter


def make_router(svc) -> APIRouter:
    """Роут поиска: старый формат для scope=chapters."""
    r = APIRouter(tags=["search"])

    @r.get("/search")
    def search(q: str, scope: str = "all", limit: int = 10, mode: str = "hybrid"):
        result = svc.search(q, scope, limit, mode=mode)
        # v1-совместимость: /api/search?q= отдавал список чанков
        if scope == "chapters":
            return result.get("chunks", [])
        return result

    return r
