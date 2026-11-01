"""Инструменты модуля research: web_search/academic_search/search_providers, web_read, github."""

from pathlib import Path

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec
from . import github


class SearchArgs(BaseModel):
    """web_search: поиск в интернете."""

    query: str = Field(max_length=300)
    limit: int = 6


class NoArgs(BaseModel):
    """search_providers: без аргументов."""


class ReadArgs(BaseModel):
    """web_read: текст страницы порционно (offset/next_offset)."""

    url: str = Field(max_length=500)
    offset: int = 0
    limit: int = Field(default=6000, ge=500, le=24000)


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


class VideoSearchArgs(BaseModel):
    """youtube_search: видео по теме."""

    query: str = Field(max_length=300)
    limit: int = 5


def _yt_search(query: str, limit: int, proxy: str = "") -> list[dict]:
    """yt-dlp ytsearch — прямой YouTube-поиск (в РФ часто замедлен, поэтому короткий таймаут)."""
    import subprocess

    cmd = [
        "yt-dlp",
        f"ytsearch{max(1, min(10, limit))}:{query}",
        "--flat-playlist",
        "--no-warnings",
        "--retries",
        "1",
        "--socket-timeout",
        "8",
        "--print",
        "%(id)s\x1f%(title)s\x1f%(channel)s\x1f%(duration)s",
    ]
    if proxy:
        cmd[1:1] = ["--proxy", proxy]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    results = []
    for line in (out.stdout or "").splitlines():
        parts = line.split("\x1f")
        if len(parts) >= 2 and parts[0]:
            vid, title = parts[0], parts[1]
            channel = parts[2] if len(parts) > 2 else ""
            dur = parts[3] if len(parts) > 3 and parts[3] not in ("NA", "None") else ""
            snippet = " · ".join(x for x in [channel, f"{dur} сек" if dur else ""] if x)
            results.append(
                {
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "snippet": f"видео · {snippet}" if snippet else "видео",
                }
            )
    return results


def research_tools(c) -> list[ToolSpec]:
    """Инструменты ресёрча."""
    svc = c.research

    def web_search(args: SearchArgs, ctx: ToolContext):
        del ctx
        return svc.search(args.query, args.limit)

    def academic_search(args: SearchArgs, ctx: ToolContext):
        del ctx
        return svc.academic(args.query, args.limit)

    def search_providers(args: NoArgs, ctx: ToolContext):
        del ctx, args
        return svc.providers_view()

    def youtube_search(args: VideoSearchArgs, ctx: ToolContext):
        del ctx
        note = ""
        try:
            results = _yt_search(args.query, args.limit, proxy=getattr(c.settings, "yt_proxy", "") or "")
        except Exception:  # noqa: BLE001 — YouTube из сети часто замедлен: фолбэк на веб-поиск
            results = []
        if not results:
            web = svc.search(f"{args.query} site:youtube.com", args.limit)
            results = web.get("results") or []
            note = f"прямым поиском пусто, взял из веб-поиска ({web.get('provider', '?')})"
            if not results:
                web = svc.search(f"{args.query} видео youtube", args.limit)
                results = web.get("results") or []
                note = f"ютуб-поиск недоступен, показываю веб ({web.get('provider', '?')})"
        return {
            "query": args.query,
            "count": len(results[: args.limit]),
            "results": results[: args.limit],
            **({"note": note} if note else {}),
        }

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
                "Научные статьи по теме: агрегат arXiv (препринты) + OpenAlex (библиография) "
                "+ Semantic Scholar (цитирования), с дедупом. У каждой статьи поле provider "
                "(arxiv/openalex/semantic_scholar); сводка по провайдерам и failures — в поле providers. "
                "Для фундаментальных/математических тем даёт первоисточники лучше веба."
            ),
            args_model=SearchArgs,
            handler=academic_search,
            label="Ищу статьи",
        ),
        ToolSpec(
            name="search_providers",
            module="research",
            description=(
                "Где агент ищет: категории web/academic/video со списком провайдеров и их состоянием "
                "(enabled, ключ задан / без ключа). Зови, когда пользователю важно, какие источники охвачены."
            ),
            args_model=NoArgs,
            handler=search_providers,
            label="Показываю провайдеров поиска",
        ),
        ToolSpec(
            name="youtube_search",
            module="research",
            description=(
                "Видео по теме (YouTube): качественное видео — отдельный пласт материала для изучения. "
                "Найденное добавляй в Библиотеку: add_source(kind='video', url, title) + process_source."
            ),
            args_model=VideoSearchArgs,
            handler=youtube_search,
            label="Ищу видео",
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
            truncatable=False,
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
