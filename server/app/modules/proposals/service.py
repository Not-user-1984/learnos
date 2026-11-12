"""Сервис предложений (B-010): агрегация и решения человека.

Мердж в main — только человек: accept ветки = push + PR, не больше.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import httpx

from ...kernel.clock import SystemClock, now_iso
from ...kernel.errors import NotFound, ValidationFailed
from .infra.sql_repo import DecisionRepository

TASK_FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.S)

GITHUB_API = "https://api.github.com"
# признаки отказа auth в выводе git push — к ним добавляем подсказку про токен
PUSH_AUTH_HINTS = ("Authentication failed", "could not read Username", "403", "401", "permission")


def _frontmatter(text: str) -> dict:
    m = TASK_FRONTMATTER.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


class ProposalsService:
    """Задачи-идеи агентов, ветки agent/*, черновики правок промптов."""

    def __init__(self, uow, revision, tuning, settings, repo=None) -> None:
        self._uow = uow
        self._revision = revision
        self._tuning = tuning
        self._settings = settings
        self._decisions = repo or DecisionRepository()
        self._clock = SystemClock()

    # --- агрегация ---

    def list(self) -> dict:
        with self._uow() as uow:
            decided = self._decisions.all(uow.session)
        tasks = [t for t in self._idea_tasks() if decided.get(("task", t["id"])) is None]
        branches = [
            b
            for b in self._revision.prepared_branches()
            if decided.get(("branch", b.get("branch", ""))) is None
        ]
        prompts = [
            c
            for c in self._tuning.changes(status="pending")
            if decided.get(("prompt", str(c.get("id")))) is None
        ]
        return {"tasks": tasks, "branches": branches, "prompt_changes": prompts}

    def _idea_tasks(self) -> list[dict]:
        """Задачи агентов со статусом idea: task_ai/tasks (git) + data/proposals/tasks (B-011).

        Человек в «Предложениях» видит только агентское: метка `author: agent`
        (ставит create_task_file) или старое `from: ревизия кода…`; задачи из
        data создаёт только сервис — они агентские по определению.
        """
        out: list[dict] = []
        root = self._repo_root()
        git_dir = root / "task_ai" / "tasks"
        if git_dir.is_dir():
            for path in sorted(git_dir.glob("T-*.md")):
                meta = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
                if meta.get("status") != "idea":
                    continue
                origin = meta.get("from", "")
                if meta.get("author") != "agent" and not origin.startswith("ревизия кода"):
                    continue  # бэклог человека — не предложение агента (B-011)
                out.append(
                    {
                        "id": meta.get("id") or path.stem,
                        "title": meta.get("title") or path.stem,
                        "from": origin,
                        "path": f"task_ai/tasks/{path.name}",
                        "source": "git",
                    }
                )
        data_dir = self._settings.data_dir / "proposals" / "tasks"
        if data_dir.is_dir():
            for path in sorted(data_dir.glob("T-*.md")):
                meta = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
                if meta.get("status") != "idea":
                    continue
                out.append(
                    {
                        "id": meta.get("id") or path.stem,
                        "title": meta.get("title") or path.stem,
                        "from": meta.get("from", ""),
                        "path": f"data/proposals/tasks/{path.name}",
                        "source": "data",
                        # полный текст: файл вне git-дерева — в бэклог его переносит
                        # человек копированием (B-011)
                        "text": path.read_text(encoding="utf-8", errors="replace"),
                    }
                )
        return out

    def _repo_root(self) -> Path:
        raw = (self._settings.repo_root or "").strip()
        return Path(raw) if raw else Path.cwd()

    # --- решения ---

    def decide(self, kind: str, ref: str, decision: str) -> dict:
        """Принять/отклонить: задача — метка в БД; ветка — push+PR или удаление; промпт — применение."""
        if decision not in {"accepted", "rejected"}:
            raise ValidationFailed("decision: accepted | rejected")
        extra: dict = {}
        if kind == "branch":
            extra = self._accept_branch(ref) if decision == "accepted" else {}
        elif kind == "task" and decision == "accepted":
            extra = self._task_copy_text(ref)
        with self._uow() as uow:
            self._decisions.decide(uow.session, kind, ref, decision, now_iso(self._clock))
        return {"ok": True, "kind": kind, "ref": ref, "decision": decision, **extra}

    def _task_copy_text(self, task_id: str) -> dict:
        """Задача из data (прод): текст для переноса в бэклог руками (B-011)."""
        for t in self._idea_tasks():
            if t["id"] == task_id and t.get("source") == "data":
                return {"task_text": t["text"]}
        return {}

    def _accept_branch(self, branch: str) -> dict:
        """Ветка agent/* → GitHub: push и PR (мердж — только человек)."""
        if not re.match(r"^agent/[A-Za-z0-9._-]+$", branch):
            raise ValidationFailed("accept доступен только веткам agent/*")
        root = self._repo_root()
        if not (root / ".git").exists():
            raise NotFound(f"{root} — не git-репозиторий")
        # полный refspec: короткое имя ветки неоднозначно, если существует тег с тем же именем
        argv = [
            "git",
            *self._push_auth_args(),
            "push",
            "origin",
            f"refs/heads/{branch}:refs/heads/{branch}",
        ]
        try:
            push = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as e:
            raise ValidationFailed(
                "git не найден в окружении сервиса — push ветки невозможен (нужен git в образе)"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ValidationFailed("git push: таймаут 120 с — попробуйте ещё раз") from e
        if push.returncode != 0:
            tail = (push.stderr or push.stdout or "")[-300:].strip()
            hint = (
                " — проверьте токен доступа к GitHub (LEARNOS_GITHUB_TOKEN)"
                if any(h in tail for h in PUSH_AUTH_HINTS)
                else ""
            )
            raise ValidationFailed(f"push ветки {branch} не удался: {tail}{hint}")
        pr_url = self._create_pr(root, branch)
        return {
            "pushed": True,
            "pr_url": pr_url,
            "compare_url": self._compare_url(root, branch),
        }

    def _push_auth_args(self) -> list[str]:
        """Креды push из env-токена: хелпер-файл в data (токен не светится в argv).

        Без токена — пусто: push использует creds окружения (локальная разработка).
        """
        token = (getattr(self._settings, "github_token", "") or "").strip()
        if not token:
            return []
        helper = self._settings.data_dir / "git-cred.sh"
        try:
            if not helper.exists():
                helper.write_text(
                    '#!/bin/sh\necho "username=x-access-token"\necho "password=$LEARNOS_GITHUB_TOKEN"\n',
                    encoding="utf-8",
                )
                helper.chmod(0o700)
        except OSError:
            return []  # data недоступна для записи — push попробует creds окружения
        # пустое значение сбрасывает системных хелперов: используем только наш токен
        return ["-c", "credential.helper=", "-c", f"credential.helper={helper}"]

    def _create_pr(self, root: Path, branch: str) -> str | None:
        url = self._pr_via_gh(root, branch)
        if url:
            return url
        return self._pr_via_api(root, branch)

    def _pr_via_gh(self, root: Path, branch: str) -> str | None:
        try:
            pr = subprocess.run(
                ["gh", "pr", "create", "--fill", "--head", branch],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if pr.returncode == 0:
                return pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else None
        except (OSError, subprocess.SubprocessError):
            pass
        return None  # gh нет/не настроен — пробуем REST с env-токеном

    def _pr_via_api(self, root: Path, branch: str) -> str | None:
        """PR через GitHub REST с токеном сервиса (gh в контейнере нет, B-011)."""
        token = (getattr(self._settings, "github_token", "") or "").strip()
        slug = self._repo_slug(root)
        if not token or not slug:
            return None
        summary = next(
            (
                b.get("summary") or b.get("message")
                for b in self._revision.prepared_branches()
                if b.get("branch") == branch
            ),
            None,
        )
        title = f"{branch}: {summary}" if summary else branch
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = httpx.post(
                f"{GITHUB_API}/repos/{slug}/pulls",
                headers=headers,
                json={"title": title[:120], "head": branch, "base": "main"},
                timeout=30,
            )
            if resp.status_code in (200, 201):
                return str(resp.json().get("html_url") or "") or None
            if resp.status_code == 422:  # PR уже есть — отдаём ссылку на него
                listed = httpx.get(
                    f"{GITHUB_API}/repos/{slug}/pulls",
                    headers=headers,
                    params={"head": f"{slug.split('/')[0]}:{branch}", "state": "open"},
                    timeout=30,
                )
                items = listed.json() if listed.status_code == 200 else []
                if isinstance(items, list) and items:
                    return str(items[0].get("html_url") or "") or None
        except httpx.HTTPError:
            return None
        return None  # PR не создан — человек пройдёт по compare_url

    def _repo_slug(self, root: Path) -> str | None:
        """owner/repo из remote origin (поддержка https и ssh-вида)."""
        try:
            out = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", out)
        return m.group(1) if m else None

    def _compare_url(self, root: Path, branch: str) -> str | None:
        slug = self._repo_slug(root)
        return f"https://github.com/{slug}/compare/main...{branch}" if slug else None
