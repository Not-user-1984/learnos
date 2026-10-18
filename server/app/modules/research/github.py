"""GitHub-клиент для idea-scout: чтение репозиториев без клона (REST API).

Токен GITHUB_TOKEN необязателен (без него лимит 60 запросов/час, с ним — 5000).
"""

import logging
import os
import re

import httpx

log = logging.getLogger("learnos.research")

GH = "https://api.github.com"
_MAX_TREE = 400  # путей в компактном дереве
_MAX_FILE = 20_000  # символов файла в ответе инструменту

_GH_URL = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def parse_repo_ref(ref: str) -> str:
    """URL или owner/name → 'owner/name'; ValueError, если не похоже на репозиторий."""
    m = _GH_URL.search(ref) if "github.com" in ref else None
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", ref.strip()):
        return ref.strip()
    raise ValueError(f"не похоже на GitHub-репозиторий: {ref[:120]}")


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "learnos-idea-scout"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str, **kw) -> httpx.Response:
    r = httpx.get(f"{GH}{path}", headers=_headers(), timeout=20, follow_redirects=True, **kw)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise ValueError("GitHub API rate limit — задай GITHUB_TOKEN (см. secrets-map)")
    r.raise_for_status()
    return r


def repo_overview(ref: str, readme_chars: int = 12_000) -> dict:
    """Мета + README + компактное дерево файлов — стартовая карта репозитория."""
    repo = parse_repo_ref(ref)
    meta = _get(f"/repos/{repo}").json()
    try:
        readme = _get(f"/repos/{repo}/readme", headers={"Accept": "application/vnd.github.raw"}).text
    except Exception:  # noqa: BLE001 — readme не критичен
        readme = ""
    tree_lines: list[str] = []
    try:
        branch = meta.get("default_branch", "HEAD")
        tree = _get(f"/repos/{repo}/git/trees/{branch}", params={"recursive": "1"}).json()
        truncated = tree.get("truncated", False)
        dirs: dict[str, int] = {}
        files: list[str] = []
        for it in tree.get("tree", []):
            path = it.get("path", "")
            if it.get("type") == "blob":
                top = "/".join(path.split("/")[:-1]) or "(корень)"
                dirs[top] = dirs.get(top, 0) + 1
            if it.get("type") == "blob" and len(files) < _MAX_TREE:
                files.append(path)
        tree_lines = [f"{d}/ ({n} файлов)" for d, n in sorted(dirs.items())[:40]]
    except Exception as e:  # noqa: BLE001
        truncated, files = False, []
        tree_lines = [f"дерево недоступно: {e}"]
    return {
        "repo": repo,
        "description": meta.get("description") or "",
        "stars": meta.get("stargazers_count", 0),
        "language": meta.get("language") or "",
        "topics": meta.get("topics") or [],
        "default_branch": meta.get("default_branch", ""),
        "readme": readme[:readme_chars],
        "readme_truncated": len(readme) > readme_chars,
        "dirs": tree_lines,
        "files_sample": files[:80],
        "tree_truncated": truncated,
        "note": "файлы читай github_file по мере необходимости, не всё сразу",
    }


def repo_file(ref: str, path: str) -> dict:
    """Текст файла репозитория (обрезка до _MAX_FILE символов)."""
    repo = parse_repo_ref(ref)
    r = _get(f"/repos/{repo}/contents/{path.lstrip('/')}", headers={"Accept": "application/vnd.github.raw"})
    text = r.text
    return {
        "repo": repo,
        "path": path,
        "chars": len(text),
        "truncated": len(text) > _MAX_FILE,
        "content": text[:_MAX_FILE],
    }
