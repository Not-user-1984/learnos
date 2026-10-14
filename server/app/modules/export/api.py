"""REST экспорта."""

from fastapi import APIRouter
from fastapi.responses import Response


def make_router(svc) -> APIRouter:
    """Роут выгрузок: md — текст, zip — файл."""
    r = APIRouter(prefix="/export", tags=["export"])

    @r.get("")
    def export(scope: str = "all", id: str | None = None, format: str = "md", max_chars: int | None = None):
        if format == "zip":
            data = svc.zip(scope, id)
            return Response(
                content=data,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="learnos-{scope}.zip"'},
            )
        result = svc.markdown(scope, id, max_chars)
        return Response(
            content=result["content"],
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
        )

    return r
