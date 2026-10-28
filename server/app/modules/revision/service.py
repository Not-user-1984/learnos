"""Ревизия кодовой базы агентом (T-038): read-only доступ к репо, задачи, ветки agent/*.

Ступень 1 — auditor читает репозиторий и создаёт файлы задач. Ступень 2 —
подготовка правок в отдельной ветке через git worktree (рабочая копия не
покидает main), коммит — только с зелёными проверками; применение/пуш —
всегда за человеком. Guard-лист закрывает ядро системы и сам модуль ревизии.
"""

import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from ...kernel.clock import SystemClock, now_iso
from ...kernel.errors import Conflict, NotFound, ValidationFailed

# каталоги, не показываемые аудитору: рантайм-данные, кэши, зависимости
REPO_SKIP_DIRS = frozenset(
    {
        ".git",
        ".idea",
        ".venv",
        ".DS_Store",
        "__pycache__",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".uv",
        "data",
        "kb",
        "node_modules",
    }
)
REPO_LIST_MAX_DEPTH = 8
REPO_LIST_MAX_ENTRIES = 400
REPO_READ_MAX_BYTES = 2_000_000
REPO_READ_DEFAULT_CHARS = 20_000
REPO_READ_MAX_CHARS = 100_000

# файлы секретов недоступны аудитору ни по чтению, ни в листинге: рабочая копия
# на проде содержит /opt/learnos/.env с ключами LLM (инцидент-превенция, ревью T-038)
SECRET_FILE_RE = re.compile(r"^\.env(\..+)?$|\.pem$|\.key$|id_rsa", re.IGNORECASE)

# пути, закрытые для правок агентом навсегда (T-034, решение по этапу D):
# точка входа, миграции, LLM-слой, деплой, весь веб, задачи, сам guard-модуль
GUARDED_PREFIXES = (
    "server/app/bootstrap.py",
    "server/app/main.py",
    "server/alembic/",
    "server/app/llm/",
    "server/config/llm.yaml",
    "web/",
    "task_ai/",
    "deploy/",
    "server/app/modules/revision/",
)
DOCKER_COMPOSE_PREFIX = "docker-compose"

BRANCH_RE = re.compile(r"^agent/[a-z0-9][a-z0-9._-]{0,40}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
TASK_ID_RE = re.compile(r"^T-(\d{3,4})")

# команды проверок сервера — те же, что в воркфлоу разработчика; (имя, argv, таймаут)
SERVER_CHECKS: tuple[tuple[str, list[str], int], ...] = (
    ("ruff", ["uv", "run", "ruff", "check", "."], 120),
    ("ruff-format", ["uv", "run", "ruff", "format", "--check", "."], 120),
    ("lint-imports", ["uv", "run", "lint-imports"], 180),
    ("pytest", ["uv", "run", "pytest", "-q"], 900),
)
CHECK_LOG_TAIL_CHARS = 2000

GIT_TIMEOUT = 60


def _clip(text: str, limit: int) -> str:
    """Хвост лога для результата инструмента."""
    return text if len(text) <= limit else "…" + text[-limit:]


class RevisionService:
    """Read-only ревизия репо + подготовка веток agent/* в git worktree."""

    def __init__(self, settings, clock: SystemClock | None = None) -> None:
        self._settings = settings
        self._clock = clock or SystemClock()

    # --- корень репо ---

    def _root(self) -> Path:
        """Корень репозитория из настроек; пусто — ревизия не настроена."""
        raw = self._settings.repo_root.strip()
        if not raw:
            raise NotFound("ревизия не настроена: задайте корень репозитория (LEARNOS_REPO_ROOT)")
        root = Path(raw).expanduser()
        if not root.is_dir():
            raise NotFound(f"корень репозитория недоступен: {root}")
        return root.resolve()

    def _resolve(self, rel: str) -> Path:
        """Относительный путь внутри репо; абсолютные и «..» запрещены; секреты недоступны."""
        posix = PurePosixPath(rel)
        if not rel or posix.is_absolute() or ".." in posix.parts:
            raise ValidationFailed(f"путь запрещён (нужен относительный, от корня репозитория): {rel}")
        if SECRET_FILE_RE.search(posix.name):
            raise ValidationFailed("файлы секретов (.env, ключи) недоступны для ревизии")
        full = (self._root() / rel).resolve()
        if not full.is_relative_to(self._root()):
            raise ValidationFailed(f"путь вне репозитория: {rel}")
        return full

    # --- ступень 1: чтение репо ---

    def repo_list(self, path: str = "") -> dict:
        """Дерево каталогов репозитория без рантайм-данных и кэшей."""
        root = self._root()
        base = self._resolve(path) if path else root
        if not base.is_dir():
            raise NotFound(f"каталог не найден: {path}")
        entries: list[str] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            if len(PurePosixPath(rel_dir).parts) >= REPO_LIST_MAX_DEPTH:
                dirnames[:] = []
            dirnames[:] = sorted(d for d in dirnames if d not in REPO_SKIP_DIRS)
            for name in sorted(dirnames):
                entries.append(f"{rel_dir}/{name}/" if rel_dir != "." else f"{name}/")
            for name in sorted(filenames):
                if SECRET_FILE_RE.search(name):
                    continue
                entries.append(f"{rel_dir}/{name}" if rel_dir != "." else name)
            if len(entries) > REPO_LIST_MAX_ENTRIES:
                truncated = True
                break
        return {
            "root": path or ".",
            "entries": entries[:REPO_LIST_MAX_ENTRIES],
            "truncated": truncated,
            "note": "директории с «/»; data/, kb/, .git и кэши скрыты",
        }

    def repo_read(self, path: str, max_chars: int = REPO_READ_DEFAULT_CHARS) -> dict:
        """Прочитать текстовый файл репозитория (с лимитом размера)."""
        full = self._resolve(path)
        if not full.is_file():
            raise NotFound(f"файл не найден: {path}")
        if full.stat().st_size > REPO_READ_MAX_BYTES:
            raise ValidationFailed(
                f"файл больше {REPO_READ_MAX_BYTES // 1_000_000} МБ — прочитать нельзя,"
                " укажите нужный фрагмент задачей"
            )
        raw = full.read_bytes()
        if b"\x00" in raw[:1024]:
            raise ValidationFailed("бинарный файл — чтение только для текстов")
        text = raw.decode("utf-8", errors="replace")
        limit = max(0, min(max_chars, REPO_READ_MAX_CHARS))
        truncated = len(text) > limit
        return {
            "path": path,
            "size": len(raw),
            "truncated": truncated,
            "content": text[:limit],
        }

    # --- ступень 1: задачи ---

    def create_task_file(self, title: str, body: str, author: str = "") -> dict:
        """Создать файл задачи в task_ai/tasks/ по шаблону; только создание."""
        root = self._root()
        tasks_dir = root / "task_ai" / "tasks"
        if not tasks_dir.is_dir():
            raise NotFound("task_ai/tasks не найден — ревизия работает только в репозитории LearnOS")
        title = " ".join(title.split())
        if not title:
            raise ValidationFailed("нужен заголовок задачи")
        if not body.strip():
            raise ValidationFailed("нужно описание задачи")
        task_id = f"T-{self._next_task_number(root):03d}"
        slug = SLUG_RE.sub("-", title.lower()).strip("-")[:40]
        name = f"{task_id}-{slug}.md" if slug else f"{task_id}.md"
        path = tasks_dir / name
        if path.exists():
            raise Conflict(f"файл задачи уже существует: {path.name}")
        content = (
            "---\n"
            f"id: {task_id}\n"
            f"title: {title}\n"
            "status: idea\n"
            "priority: medium\n"
            f"from: ревизия кода (auditor{f'/{author}' if author else ''})\n"
            f"created: {now_iso(self._clock)[:10]}\n"
            "---\n\n"
            "## Что нужно\n\n"
            f"{body.strip()}\n\n"
            "## Критерии готовности\n\n"
            "- [ ] (сформулирует разработчик)\n\n"
            "## Заметки\n\n"
            "(создано агентом-аудитором)\n"
        )
        path.write_text(content, encoding="utf-8")
        return {
            "task_id": task_id,
            "file": f"task_ai/tasks/{name}",
            "message": f"задача {task_id} создана со статусом idea",
        }

    def _next_task_number(self, root: Path) -> int:
        """Максимальный существующий номер задачи (tasks + архив) + 1."""
        numbers = [0]
        for folder in (root / "task_ai" / "tasks", root / "task_ai" / "archive"):
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                m = TASK_ID_RE.match(f.name)
                if m:
                    numbers.append(int(m.group(1)))
        return max(numbers) + 1

    # --- ступень 2: ветки agent/* ---

    def git_prepare_change(
        self, branch: str, files: list[dict], commit_message: str, author: str = ""
    ) -> dict:
        """Подготовить ветку agent/* в git worktree и закоммитить правки.

        Коммит — только с зелёными проверками сервера; при красных worktree и
        ветка удаляются. main и рабочая копия не затрагиваются.
        """
        root = self._root()
        if not (root / ".git").exists():
            raise ValidationFailed(f"{root} — не git-репозиторий")
        if not BRANCH_RE.match(branch):
            raise ValidationFailed(
                "ветка агента: agent/<имя> — латиница/цифры/._- после префикса, до 41 символа"
            )
        message = commit_message.strip()
        if not message:
            raise ValidationFailed("нужно сообщение коммита")
        if not files:
            raise ValidationFailed("список файлов пуст")

        rel_files: list[tuple[str, str]] = []
        for item in files:
            rel = self._relpath(item.get("path", ""))
            rel_files.append((rel, item.get("content", "")))
        violations = [rel for rel, _ in rel_files if self._is_guarded(rel)]
        if violations:
            return {
                "error": "guarded_paths",
                "paths": violations,
                "message": (
                    "эти пути закрыты для правок агентом (ядро системы, деплой, веб, задачи, "
                    "сам модуль ревизии) — сформулируйте предложение задачей create_task_file"
                ),
            }

        created_today = self._branches_created_today()
        if created_today >= self._settings.git_branch_budget:
            return {
                "error": "budget_exceeded",
                "message": (
                    f"дневной бюджет подготовленных веток исчерпан ({created_today} из "
                    f"{self._settings.git_branch_budget}) — продолжение завтра или руками человека"
                ),
            }

        worktree = self._worktree_path(branch)
        if worktree.exists() or self._branch_exists(root, branch):
            return {
                "error": "branch_exists",
                "message": f"ветка {branch} уже подготовлена — правки применяет человек",
            }

        self._git(root, ["worktree", "add", str(worktree), "-b", branch])
        try:
            for rel, content in rel_files:
                target = worktree / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            checks = self._run_checks_in(worktree)
            if not checks["ok"]:
                self._cleanup_branch(root, worktree, branch)
                return {
                    "error": "checks_failed",
                    "message": "проверки не прошли — ветка не создана, исправьте правки и повторите",
                    "checks": checks,
                }
            self._git(worktree, ["add", "--", *[rel for rel, _ in rel_files]])
            self._git(
                worktree,
                [
                    "-c",
                    "user.name=learnos-auditor",
                    "-c",
                    f"user.email={author or 'auditor'}@learnos.local",
                    "commit",
                    "-m",
                    message[:500],
                ],
            )
            sha = self._git(worktree, ["rev-parse", "HEAD"]).stdout.strip()
            diffstat = self._git(worktree, ["show", "--stat", "--format=", "HEAD"]).stdout
            diff = self._diff_lines(self._git(worktree, ["show", "--format=", "HEAD"]).stdout)
            self._journal(branch, sha, message, [rel for rel, _ in rel_files])
            return {
                "branch": branch,
                "commit": sha[:10],
                "worktree": str(worktree),
                "message": f"ветка {branch} подготовлена (commit {sha[:10]}) — применение за человеком",
                "checks": checks,
                "diffstat": _clip(diffstat, 1500),
                "_card": {
                    "type": "git_change",
                    "branch": branch,
                    "commit": sha[:10],
                    "summary": message.splitlines()[0][:120],
                    "files": [rel for rel, _ in rel_files],
                    "diff": diff,
                    "checks": "passed",
                },
            }
        except subprocess.CalledProcessError as e:
            self._cleanup_branch(root, worktree, branch)
            stderr = e.stderr if isinstance(e.stderr, str) else ""
            raise ValidationFailed(f"git: {_clip(stderr or str(e), 400)}") from e

    def reject_branch(self, branch: str) -> dict:
        """Удалить подготовленную ветку агента (worktree, ветка, запись дневника)."""
        if not BRANCH_RE.match(branch):
            raise ValidationFailed("удаление — только для веток агента agent/<имя>")
        root = self._root()
        worktree = self._worktree_path(branch)
        if not self._branch_exists(root, branch) and not worktree.exists():
            raise NotFound(f"ветка {branch} не найдена")
        self._cleanup_branch(root, worktree, branch)
        return {"ok": True, "branch": branch, "message": f"ветка {branch} и worktree удалены"}

    def prepared_branches(self) -> list[dict]:
        """Подготовленные ветки из дневника (для UI и инспекции)."""
        journal_dir = self._journal_dir()
        if not journal_dir.is_dir():
            return []
        return sorted(
            (json.loads(p.read_text(encoding="utf-8")) for p in journal_dir.glob("*.json")),
            key=lambda b: b.get("created_at", ""),
            reverse=True,
        )

    def run_checks(self, branch: str | None = None) -> dict:
        """Прогнать проверки сервера в worktree ветки или в рабочей копии."""
        root = self._root()
        where = root
        if branch:
            if not BRANCH_RE.match(branch):
                raise ValidationFailed("ветка агента: agent/<имя>")
            where = self._worktree_path(branch)
            if not where.is_dir():
                raise NotFound(f"worktree ветки {branch} не найден")
        return self._run_checks_in(where)

    # --- внутреннее ---

    def _relpath(self, rel: str) -> str:
        """Нормализация относительного пути файла (для записи)."""
        posix = PurePosixPath(rel.strip())
        if not rel.strip() or posix.is_absolute() or ".." in posix.parts:
            raise ValidationFailed(f"путь файла запрещён: {rel}")
        return posix.as_posix()

    def _is_guarded(self, rel: str) -> bool:
        if rel.startswith(GUARDED_PREFIXES):
            return True
        first = rel.split("/", 1)[0]
        return first.startswith(DOCKER_COMPOSE_PREFIX)

    def _worktree_path(self, branch: str) -> Path:
        return self._settings.data_dir / "git-worktrees" / branch.replace("/", "__")

    def _journal_dir(self) -> Path:
        return self._settings.data_dir / "git-branches"

    def _branches_created_today(self) -> int:
        journal = self._journal_dir()
        if not journal.is_dir():
            return 0
        today = now_iso(self._clock)[:10]
        return sum(1 for _ in journal.glob(f"{today}__*.json"))

    def _journal(self, branch: str, sha: str, message: str, files: list[str]) -> None:
        journal = self._journal_dir()
        journal.mkdir(parents=True, exist_ok=True)
        today = now_iso(self._clock)[:10]
        name = f"{today}__{branch.replace('/', '_')}.json"
        (journal / name).write_text(
            json.dumps(
                {
                    "branch": branch,
                    "commit": sha[:10],
                    "message": message.splitlines()[0][:200],
                    "files": files,
                    "created_at": now_iso(self._clock),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _branch_exists(self, root: Path, branch: str) -> bool:
        try:
            self._git(root, ["rev-parse", "--verify", f"refs/heads/{branch}"])
            return True
        except subprocess.CalledProcessError:
            return False

    def _cleanup_branch(self, root: Path, worktree: Path, branch: str) -> None:
        """Удалить worktree, ветку и дневник — тихо, по мере наличия."""
        if worktree.exists():
            self._git(root, ["worktree", "remove", "--force", str(worktree)])
        if self._branch_exists(root, branch):
            self._git(root, ["branch", "-D", branch])
        today = now_iso(self._clock)[:10]
        marker = self._journal_dir() / f"{today}__{branch.replace('/', '_')}.json"
        marker.unlink(missing_ok=True)

    def _run_checks_in(self, repo_dir: Path) -> dict:
        """Команды проверок сервера; результат — коды выхода и хвосты логов."""
        results = []
        ok = True
        for name, argv, timeout in SERVER_CHECKS:
            try:
                proc = subprocess.run(
                    argv, cwd=repo_dir / "server", capture_output=True, text=True, timeout=timeout
                )
                code, log = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
            except FileNotFoundError as e:
                code, log = 127, f"{argv[0]}: не найден ({e.filename})"
            except subprocess.TimeoutExpired:
                code, log = 124, f"{name}: таймаут {timeout}s"
            ok = ok and code == 0
            results.append({"check": name, "exit_code": code, "log": _clip(log, CHECK_LOG_TAIL_CHARS)})
        return {"ok": ok, "results": results}

    def _git(self, cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
        """git с явными аргументами (без shell); ошибка — CalledProcessError."""
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=True,
        )

    def _diff_lines(self, diff_text: str, limit: int = 300) -> list[dict]:
        """Унифицированный дифф в компактный вид для карточки чата."""
        out = []
        for line in diff_text.splitlines():
            if line.startswith("@@"):
                out.append({"op": "@", "line": line})
            elif line.startswith("+") and not line.startswith("+++"):
                out.append({"op": "+", "line": line[1:]})
            elif line.startswith("-") and not line.startswith("---"):
                out.append({"op": "-", "line": line[1:]})
            if len(out) >= limit:
                break
        return out
