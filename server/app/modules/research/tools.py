"""Инструменты модуля research: web_search и web_read (доступны всем агентам)."""

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class SearchArgs(BaseModel):
    """web_search: поиск в интернете."""

    query: str = Field(max_length=300)
    limit: int = 6


class ReadArgs(BaseModel):
    """web_read: текст страницы порционно (offset/next_offset)."""

    url: str = Field(max_length=500)
    offset: int = 0
    limit: int = 12000


def research_tools(c) -> list[ToolSpec]:
    """Инструменты ресёрча."""
    svc = c.research

    def web_search(args: SearchArgs, ctx: ToolContext):
        del ctx
        return svc.search(args.query, args.limit)

    def web_read(args: ReadArgs, ctx: ToolContext):
        del ctx
        try:
            page = svc.extract(args.url)
        except Exception as e:  # noqa: BLE001 — битый URL не должен ронять агент
            return {"error": "fetch_failed", "message": str(e)[:300]}
        win = svc.window(page["text"], args.offset, args.limit)
        return {
            "url": args.url,
            "title": page["title"],
            "provider_note": "полный текст — окнами, листай offset",
            **win,
        }

    return [
        ToolSpec(
            name="web_search",
            module="research",
            description=(
                "Поиск в интернете (бесплатный движок). Возвращает title/url/snippet — "
                "покажи ссылки пользователю."
            ),
            args_model=SearchArgs,
            handler=web_search,
            label="Ищу в сети",
        ),
        ToolSpec(
            name="web_read",
            module="research",
            description=(
                "Текст веб-страницы порционно (offset/next_offset) — для чтения статьи перед обсуждением."
            ),
            args_model=ReadArgs,
            handler=web_read,
            label="Читаю страницу",
        ),
    ]
