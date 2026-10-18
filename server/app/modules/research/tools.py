"""Инструменты модуля research: web_search/academic_search, web_read, github для idea-scout."""

from pathlib import Path

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec
from . import github


class SearchArgs(BaseModel):
    """web_search: поиск в интернете."""

    query: str = Field(max_length=300)
    limit: int = 6


class ReadArgs(BaseModel):
    """web_read: текст страницы порционно (offset/next_offset)."""

    url: str = Field(max_length=500)
    offset: int = 0
    limit: int = 12000


class RepoArgs(BaseModel):
    """github_repo: карта репозитория для анализа идей."""

    repo: str = Field(max_length=200)


class RepoFileArgs(BaseModel):
    """github_file: прочитать файл репозитория."""

    repo: str = Field(max_length=200)
    path: str = Field(max_length=300)


class IdeaReportArgs(BaseModel):
    """save_idea_report: сохранить отчёт idea-scout в data/ideas/."""

    title: str = Field(max_length=120)
    content: str = Field(max_length=20000)


def research_tools(c) -> list[ToolSpec]:
    """Инструменты ресёрча."""
    svc = c.research

    def web_search(args: SearchArgs, ctx: ToolContext):
        del ctx
        return svc.search(args.query, args.limit)

    def academic_search(args: SearchArgs, ctx: ToolContext):
        del ctx
        return svc.academic(args.query, args.limit)

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

    def github_repo(args: RepoArgs, ctx: ToolContext):
        del ctx
        try:
            return github.repo_overview(args.repo)
        except Exception as e:  # noqa: BLE001
            return {"error": "github_failed", "message": str(e)[:300]}

    def github_file(args: RepoFileArgs, ctx: ToolContext):
        del ctx
        try:
            return github.repo_file(args.repo, args.path)
        except Exception as e:  # noqa: BLE001
            return {"error": "github_failed", "message": str(e)[:300]}

    def save_idea_report(args: IdeaReportArgs, ctx: ToolContext):
        import os
        import re as _re
        from datetime import date

        root = Path(os.environ.get("LEARNOS_DATA_DIR", Path.cwd() / "data")) / "ideas"
        root.mkdir(parents=True, exist_ok=True)
        slug = _re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-")[:60] or "report"
        path = root / f"{date.today().isoformat()}-{slug}.md"
        path.write_text(f"# {args.title}\n\n{args.content}\n", encoding="utf-8")
        return {"ok": True, "saved": str(path), "repo_note": "отчёт лежит в data/ideas"}

    return [
        ToolSpec(
            name="web_search",
            module="research",
            description=(
                "Поиск в интернете (бесплатный движок, при пустом ответе автоматически "
                "Википедия/обсуждения). Возвращает title/url/snippet — покажи ссылки пользователю."
            ),
            args_model=SearchArgs,
            handler=web_search,
            label="Ищу в сети",
        ),
        ToolSpec(
            name="academic_search",
            module="research",
            description=(
                "Научные статьи по теме (arXiv: препринты, стабильный ключлесс-API). "
                "Для фундаментальных/математических тем даёт первоисточники лучше веба."
            ),
            args_model=SearchArgs,
            handler=academic_search,
            label="Ищу статьи",
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
        ToolSpec(
            name="github_repo",
            module="research",
            description=("Карта GitHub-репозитория (мета, README, дерево файлов) — старт анализа на идеи."),
            args_model=RepoArgs,
            handler=github_repo,
            label=lambda a: f"Смотрю репозиторий {str(a.get('repo', ''))[:40]}",
        ),
        ToolSpec(
            name="github_file",
            module="research",
            description="Текст файла из GitHub-репозитория (для idea-scout: читай ключевые файлы точечно).",
            args_model=RepoFileArgs,
            handler=github_file,
            label=lambda a: f"Читаю {str(a.get('path', ''))[:50]}",
        ),
        ToolSpec(
            name="save_idea_report",
            module="research",
            description="Сохранить отчёт idea-scout (markdown) в data/ideas/ — история найденных идей.",
            args_model=IdeaReportArgs,
            handler=save_idea_report,
            label="Сохраняю отчёт идей",
        ),
    ]
