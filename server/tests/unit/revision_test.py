"""Ревизия кода агентом (T-038): чтение репо, задачи, guard, бюджет, ветки agent/*, проверки."""

import subprocess
import sys
from pathlib import Path

import pytest

from app.kernel.config import Settings
from app.kernel.errors import NotFound, ValidationFailed
from app.modules.revision import service as revision_service
from app.modules.revision.service import RevisionService

# быстрые проверки вместо ruff/pytest: тестируем поведение обёртки, не линтеры
NOOP_CHECKS = (("noop", [sys.executable, "-c", "pass"], 30),)
FAIL_CHECKS = (("fail", [sys.executable, "-c", "import sys; print('fail'); sys.exit(1)"], 30),)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path) -> Path:
    """Мини-репозиторий LearnOS: server, web, task_ai, рантайм-каталог data."""
    root = tmp_path / "repo"
    (root / "server" / "app").mkdir(parents=True)
    (root / "server" / "app" / "x.py").write_text("X = 1\n")
    (root / "task_ai" / "tasks").mkdir(parents=True)
    (root / "task_ai" / "tasks" / "T-001-seed.md").write_text("---\nid: T-001\n---\n")
    (root / "web").mkdir()
    (root / "web" / "page.tsx").write_text("x")
    (root / "data" / "junk").mkdir(parents=True)
    (root / "data" / "junk" / "f.bin").write_text("junk")
    (root / "docker-compose.yml").write_text("services: {}\n")
    (root / ".gitignore").write_text("data/\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t.local")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def make_svc(tmp_path: Path, repo: Path, budget: int = 3) -> RevisionService:
    settings = Settings(
        data_dir=tmp_path / "data",
        kb_dir=tmp_path / "kb",
        llm_config=tmp_path / "llm-missing.yaml",
        repo_root=str(repo),
        git_branch_budget=budget,
    )
    return RevisionService(settings)


# --- ступень 1: чтение репо ---


def test_repo_list_hides_runtime_dirs(repo, tmp_path):
    out = make_svc(tmp_path, repo).repo_list()
    entries = out["entries"]
    assert "server/app/x.py" in entries
    assert "task_ai/tasks/T-001-seed.md" in entries
    assert ".gitignore" in entries  # файлы с точкой видны — скрыты только каталоги
    assert not any(e.startswith("data/") for e in entries)
    assert not any(e.startswith(".git/") for e in entries)


def test_repo_read_with_limit(repo, tmp_path):
    out = make_svc(tmp_path, repo).repo_read("server/app/x.py", max_chars=1)
    assert out["truncated"] is True
    assert out["content"] == "X"


def test_repo_read_denies_traversal(repo, tmp_path):
    svc = make_svc(tmp_path, repo)
    for bad in ("../outside", "/etc/passwd", "server/../../x", "a/../.."):
        with pytest.raises(ValidationFailed):
            svc.repo_read(bad)


def test_revision_not_configured(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", kb_dir=tmp_path / "kb", llm_config=tmp_path / "l.yaml")
    with pytest.raises(NotFound, match="не настроена"):
        RevisionService(settings).repo_list()


def test_create_task_file_next_id_and_no_overwrite(repo, tmp_path):
    svc = make_svc(tmp_path, repo)
    first = svc.create_task_file("dup check", "Найдено дублирование X", "auditor")
    assert first["task_id"] == "T-002"  # следующий после T-001
    path = repo / "task_ai" / "tasks" / "T-002-dup-check.md"
    assert path.exists()
    assert "status: idea" in path.read_text(encoding="utf-8")

    second = svc.create_task_file("dup check", "Ещё раз", "auditor")
    assert second["task_id"] == "T-003"  # новый файл, прежний не перезаписан
    assert "id: T-002" in path.read_text(encoding="utf-8")


def test_create_task_file_russian_title_without_slug(repo, tmp_path):
    out = make_svc(tmp_path, repo).create_task_file("Дублирование в сервисе", "тело задачи")
    # кириллица не транслитерируется — файл просто с номером
    assert out["file"] == "task_ai/tasks/T-002.md"


# --- ступень 2: guard ---


@pytest.mark.parametrize(
    "guarded",
    [
        "server/app/bootstrap.py",
        "server/app/main.py",
        "server/alembic/versions/0001.py",
        "server/app/llm/router.py",
        "server/config/llm.yaml",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "web/src/app/page.tsx",
        "task_ai/tasks/T-001-seed.md",
        "server/app/modules/revision/service.py",
    ],
)
def test_git_prepare_change_guard(repo, tmp_path, guarded):
    svc = make_svc(tmp_path, repo)
    out = svc.git_prepare_change(
        "agent/guard-test",
        [{"path": guarded, "content": "hacked"}],
        "правка guard-файла",
    )
    assert out["error"] == "guarded_paths"
    assert guarded in out["paths"]
    _assert_branch_absent(repo, "agent/guard-test")


def _assert_branch_absent(repo: Path, branch: str) -> None:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, f"ветка {branch} не должна существовать"


@pytest.mark.parametrize("bad", ["main", "feature/x", "agent/../x", "agent/UP", "agent/"])
def test_branch_name_must_be_agent_namespace(repo, tmp_path, bad):
    with pytest.raises(ValidationFailed):
        make_svc(tmp_path, repo).git_prepare_change(bad, [{"path": "server/app/x.py", "content": "y"}], "msg")


# --- ступень 2: ветка, бюджет, проверки ---


def test_git_prepare_change_creates_branch_in_worktree(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    svc = make_svc(tmp_path, repo)
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout

    out = svc.git_prepare_change(
        "agent/fix-x",
        [{"path": "server/app/new.py", "content": "NEW = 2\n"}],
        "добавить new.py",
    )

    assert out["branch"] == "agent/fix-x"
    assert out["_card"]["type"] == "git_change"
    assert out["diffstat"]
    # ветка и worktree на месте, файл закоммичен
    _git(repo, "rev-parse", "--verify", "refs/heads/agent/fix-x")
    worktree = tmp_path / "data" / "git-worktrees" / "agent__fix-x"
    assert (worktree / "server" / "app" / "new.py").read_text() == "NEW = 2\n"
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s", "agent/fix-x"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "добавить new.py"
    # main не тронут: HEAD рабочей копии прежний
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert head_after == head_before
    # рабочая копия осталась на main, без правок
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "new.py" not in status


def test_git_prepare_change_budget(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    svc = make_svc(tmp_path, repo, budget=2)
    for i in (1, 2):
        out = svc.git_prepare_change(
            f"agent/b-{i}", [{"path": f"server/app/b{i}.py", "content": f"B = {i}\n"}], f"правка {i}"
        )
        assert "error" not in out
    third = svc.git_prepare_change(
        "agent/b-3", [{"path": "server/app/b3.py", "content": "B = 3\n"}], "правка 3"
    )
    assert third["error"] == "budget_exceeded"
    _assert_branch_absent(repo, "agent/b-3")


def test_git_prepare_change_red_checks_leave_no_trace(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", FAIL_CHECKS)
    svc = make_svc(tmp_path, repo)
    out = svc.git_prepare_change(
        "agent/red", [{"path": "server/app/red.py", "content": "R = 1\n"}], "красная правка"
    )
    assert out["error"] == "checks_failed"
    assert out["checks"]["ok"] is False
    _assert_branch_absent(repo, "agent/red")
    assert not (tmp_path / "data" / "git-worktrees" / "agent__red").exists()


def test_git_prepare_change_twice_same_branch_rejected(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    svc = make_svc(tmp_path, repo)
    assert "error" not in svc.git_prepare_change(
        "agent/one", [{"path": "server/app/one.py", "content": "1\n"}], "первая"
    )
    second = svc.git_prepare_change("agent/one", [{"path": "server/app/one.py", "content": "2\n"}], "вторая")
    assert second["error"] == "branch_exists"


def test_reject_branch_removes_everything(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    svc = make_svc(tmp_path, repo)
    svc.git_prepare_change("agent/temp", [{"path": "server/app/t.py", "content": "T\n"}], "временная")
    assert len(svc.prepared_branches()) == 1

    out = svc.reject_branch("agent/temp")

    assert out["ok"] is True
    _assert_branch_absent(repo, "agent/temp")
    assert not (tmp_path / "data" / "git-worktrees" / "agent__temp").exists()
    assert svc.prepared_branches() == []


def test_reject_only_agent_branches(repo, tmp_path):
    with pytest.raises(ValidationFailed):
        make_svc(tmp_path, repo).reject_branch("main")


# --- run_checks ---


def test_run_checks_green_and_red(repo, tmp_path, monkeypatch):
    svc = make_svc(tmp_path, repo)
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    green = svc.run_checks()
    assert green["ok"] is True
    assert green["results"][0]["exit_code"] == 0

    monkeypatch.setattr(revision_service, "SERVER_CHECKS", FAIL_CHECKS)
    red = svc.run_checks()
    assert red["ok"] is False
    assert red["results"][0]["exit_code"] == 1
    assert red["results"][0]["log"]


def test_run_checks_in_branch_worktree(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    svc = make_svc(tmp_path, repo)
    svc.git_prepare_change("agent/chk", [{"path": "server/app/c.py", "content": "C\n"}], "для проверок")
    out = svc.run_checks(branch="agent/chk")
    assert out["ok"] is True
    with pytest.raises(NotFound):
        svc.run_checks(branch="agent/no-such")


# --- регистрация агента ---


def test_auditor_registered_in_container(container):
    spec = container.agent_registry.get("auditor")
    assert spec.tools == frozenset(
        {"repo_list", "repo_read", "create_task_file", "git_prepare_change", "run_checks"}
    )
