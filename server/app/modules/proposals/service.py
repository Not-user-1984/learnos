"""Сервис предложений (B-010): агрегация и решения человека.

Мердж в main — только человек: accept ветки = push + PR, не больше.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ...kernel.clock import SystemClock, now_iso
from ...kernel.errors import NotFound, ValidationFailed
from .infra.sql_repo import DecisionRepository

TASK_FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.S)


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
        """Задачи task_ai/tasks со статусом idea (создают auditor/repo_scout)."""
        root = self._repo_root()
        out = []
        tasks_dir = root / "task_ai" / "tasks"
        if not tasks_dir.is_dir():
            return out
        for path in sorted(tasks_dir.glob("T-*.md")):
            meta = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            if meta.get("status") != "idea":
                continue
            out.append(
                {
                    "id": meta.get("id") or path.stem,
                    "title": meta.get("title") or path.stem,
                    "from": meta.get("from", ""),
                    "path": f"task_ai/tasks/{path.name}",
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
        with self._uow() as uow:
            self._decisions.decide(uow.session, kind, ref, decision, now_iso(self._clock))
        return {"ok": True, "kind": kind, "ref": ref, "decision": decision, **extra}

    def _accept_branch(self, branch: str) -> dict:
        """Ветка agent/* → GitHub: push и PR (мердж — только человек)."""
        if not re.match(r"^agent/[A-Za-z0-9._-]+$", branch):
            raise ValidationFailed("accept доступен только веткам agent/*")
        root = self._repo_root()
        if not (root / ".git").exists():
            raise NotFound(f"{root} — не git-репозиторий")
        push = subprocess.run(
            ["git", "push", "origin", branch], cwd=root, capture_output=True, text=True, timeout=120
        )
        if push.returncode != 0:
            raise ValidationFailed(f"push не удался: {push.stderr[-300:]}")
        pr_url = self._create_pr(root, branch)
        return {"pushed": True, "pr_url": pr_url}

    def _create_pr(self, root: Path, branch: str) -> str | None:
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
        return None  # gh нет/не настроен — push есть, PR создаст человек по ссылке compare
