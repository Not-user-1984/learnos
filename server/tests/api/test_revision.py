"""REST ревизии (T-038): список подготовленных веток и отклонение agent/*."""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.kernel.config import Settings
from app.modules.revision import service as revision_service
from app.modules.revision.service import RevisionService

NOOP_CHECKS = (("noop", [sys.executable, "-c", "pass"], 30),)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "server").mkdir(parents=True)
    (root / "server" / "x.py").write_text("X = 1\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t.local")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def revision_ready(container, repo, monkeypatch):
    """Контейнер с настроенной ревизией на tmp-репо и быстрыми проверками."""
    monkeypatch.setattr(revision_service, "SERVER_CHECKS", NOOP_CHECKS)
    container.revision = RevisionService(
        Settings(
            data_dir=container.settings.data_dir,
            kb_dir=container.settings.kb_dir,
            llm_config=container.settings.llm_config,
            repo_root=str(repo),
        )
    )
    return container


def test_branches_and_reject(client: TestClient, revision_ready, repo):
    revision_ready.revision.git_prepare_change(
        "agent/api-test", [{"path": "server/new.py", "content": "N = 1\n"}], "правка из api-теста"
    )
    listed = client.get("/api/revision/branches").json()
    assert [b["branch"] for b in listed] == ["agent/api-test"]

    out = client.post("/api/revision/branch/reject", json={"branch": "agent/api-test"})
    assert out.status_code == 200
    assert client.get("/api/revision/branches").json() == []
    # ветки в git больше нет
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/heads/agent/api-test"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0

    again = client.post("/api/revision/branch/reject", json={"branch": "agent/api-test"})
    assert again.status_code == 404


def test_reject_refuses_non_agent_branch(client: TestClient, revision_ready):
    out = client.post("/api/revision/branch/reject", json={"branch": "main"})
    assert out.status_code == 422
