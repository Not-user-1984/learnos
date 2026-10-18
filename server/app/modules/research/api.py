"""REST настроек связи (поиск/прокси/vless) — раздел «Прокси и поиск» в UI."""

from fastapi import APIRouter
from pydantic import BaseModel, Field


class ConnectivityIn(BaseModel):
    """Патч настроек связи; пустое поле = сброс. Маскированные значения UI не шлёт,
    но на всякий случай ключ с '…' не затирает сохранённый."""

    search_provider: str = "chain"
    search_api_key: str = ""
    proxy_url: str = Field(default="", max_length=500)
    vless_key: str = Field(default="", max_length=2000)


def make_router(c) -> APIRouter:
    svc = c.research
    r = APIRouter(prefix="/api/connectivity", tags=["connectivity"])

    def _keep_current(key: str) -> str:
        from .connectivity import load_connectivity

        return load_connectivity(svc._uow).get(key, "")  # noqa: SLF001 — свой сервис

    @r.get("")
    def get_connectivity():
        return svc.connectivity_view()

    @r.put("")
    def put_connectivity(body: ConnectivityIn):
        patch = body.model_dump()
        for k in ("search_api_key", "vless_key"):
            if "…" in patch.get(k, ""):
                patch[k] = _keep_current(k)
        try:
            return {"ok": True, **svc.apply_connectivity(patch)}
        except ValueError as e:
            return {"ok": False, "error": str(e)[:200]}

    @r.post("/check")
    def check_connectivity():
        return svc.connectivity_check()

    return r
