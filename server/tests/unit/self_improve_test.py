"""B-010: планировщик (cron, лок, catch-up) и предложения (агрегация, решения, push+PR)."""

from datetime import datetime

from app.modules.scheduler.domain import cron_due


def test_cron_due_basic_forms():
    now = datetime(2026, 11, 11, 9, 5)  # среда
    assert cron_due("0 9 * * *", None, now) is True  # никогда не запускалось
    assert cron_due("0 9 * * *", "2026-11-10T09:00:00", now) is True  # вчера сработало
    assert cron_due("0 9 * * *", "2026-11-11T09:00:00", now) is False  # сегодня уже
    assert cron_due("*/15 * * * *", "2026-11-11T09:00:00", now) is False  # 09:00 был, 09:15 ещё не настал
    assert cron_due("*/15 * * * *", "2026-11-11T09:00:00", datetime(2026, 11, 11, 9, 14)) is False
    assert cron_due("*/15 * * * *", "2026-11-11T09:00:00", datetime(2026, 11, 11, 9, 15)) is True
    assert cron_due("0 5 * * 1", "2026-11-11T09:00:00", now) is False  # понедельник уже прошёл


def test_cron_due_catchup_after_sleep():
    """Сон хомлаба 19:00–08:30: пропущенный ночной запуск срабатывает при первом тике."""
    last = "2026-11-10T08:30:00"
    woke_up = datetime(2026, 11, 11, 8, 31)  # сутки пропуска
    assert cron_due("0 3 * * *", last, woke_up) is True


def test_scheduler_tick_lock_and_no_duplicate(container):
    """Тик: дозревшее запускается один раз; running не перезапускается."""
    svc = container.scheduler
    svc.ensure_defaults()
    svc.set_enabled("review_digest", True)

    calls = []
    svc._review_digest = lambda: calls.append(1)  # noqa: SLF001 — мок вместо Telegram
    ran = svc.tick()
    assert ran == 1 and calls == [0 + 1]

    # сразу после запуска — не дубль (last_run обновлён, due=False до следующего дня)
    assert svc.tick() == 0
    svc.set_enabled("review_digest", False)


def test_scheduler_run_now(container):
    svc = container.scheduler
    svc.ensure_defaults()
    svc._review_digest = lambda: None  # noqa: SLF001
    out = svc.run_now("review_digest")
    assert out["ok"] is True
    statuses = {s["name"]: s["last_status"] for s in svc.list()}
    assert statuses["review_digest"] == "done"


def test_proposals_list_and_decide(container, monkeypatch, tmp_path):
    """Идеи-задачи видны; решение скрывает; ветка accept → push+PR (мок subprocess)."""
    tasks_dir = tmp_path / "task_ai" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "T-901-test-idea.md").write_text(
        "---\nid: T-901\ntitle: Идея скаута\nstatus: idea\nfrom: ревизия кода (auditor)\n---\n\nтело",
        encoding="utf-8",
    )
    (tasks_dir / "T-902-done.md").write_text(
        "---\nid: T-902\ntitle: Готовое\nstatus: done\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr(type(container.proposals), "_repo_root", lambda self: tmp_path, raising=False)

    out = container.proposals.list()
    assert [t["id"] for t in out["tasks"]] == ["T-901"]

    # reject: задача исчезает из списка
    container.proposals.decide("task", "T-901", "rejected")
    assert container.proposals.list()["tasks"] == []

    # accept ветки: git push замокан (.git-каталог — чтобы прошёл guard репозитория)
    (tmp_path / ".git").mkdir()
    pushes = []
    monkeypatch.setattr(
        "app.modules.proposals.service.subprocess.run",
        lambda *a, **k: (
            pushes.append(a)
            or __import__("types").SimpleNamespace(
                returncode=0, stdout="https://github.com/x/learnos/pull/7\n", stderr=""
            )
        ),
    )
    out = container.proposals.decide("branch", "agent/fix-readme", "accepted")
    assert out["pushed"] is True
    assert pushes, "git push должен был вызваться"
    push_argv = pushes[0][0]
    assert "push" in push_argv
    # полный refspec: короткое имя неоднозначно при одноимённом теге (B-011)
    assert "refs/heads/agent/fix-readme:refs/heads/agent/fix-readme" in push_argv


def test_accept_branch_push_errors_are_clear(container, monkeypatch, tmp_path):
    """Push без git в окружении и auth-отказ — понятный текст ошибки (B-011)."""
    import pytest

    from app.kernel.errors import ValidationFailed

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(type(container.proposals), "_repo_root", lambda self: tmp_path, raising=False)

    # git нет в образе/окружении
    def no_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr("app.modules.proposals.service.subprocess.run", no_git)
    with pytest.raises(ValidationFailed, match="git не найден"):
        container.proposals.decide("branch", "agent/x", "accepted")

    # auth-отказ с подсказкой про токен
    monkeypatch.setattr(
        "app.modules.proposals.service.subprocess.run",
        lambda *a, **k: __import__("types").SimpleNamespace(
            returncode=1, stdout="", stderr="remote: Authentication failed\nfatal: 403"
        ),
    )
    with pytest.raises(ValidationFailed, match="LEARNOS_GITHUB_TOKEN"):
        container.proposals.decide("branch", "agent/x", "accepted")


def test_push_error_masks_credentials(container, monkeypatch, tmp_path):
    """Креды в stderr git push не попадают в ответ API (ревью B-011)."""
    import pytest

    from app.kernel.errors import ValidationFailed
    from app.modules.proposals.service import _mask_creds

    # прямая проверка масок: user:pass@, token@, token=…, ghp_…
    dirty = (
        "fatal: Authentication failed for "
        "'https://x-access-token:ghp_abc123SECRET@github.com/o/r.git/'\n"
        "remote: token=gho_xyz987 is revoked\n"
        "remote: Authorization: Bearer github_pat_QQ\n"
        "hint: see https://user@github.com/help"
    )
    masked = _mask_creds(dirty)
    for secret in ("ghp_abc123SECRET", "gho_xyz987", "github_pat_QQ", "x-access-token:"):
        assert secret not in masked
    assert "https://***@github.com/o/r.git/" in masked  # двойная маска: user:pass@ → ***@
    assert "https://***@github.com/help" in masked

    # и через decide: хвост stderr с кредами маскируется в тексте ошибки
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(type(container.proposals), "_repo_root", lambda self: tmp_path, raising=False)
    monkeypatch.setattr(
        "app.modules.proposals.service.subprocess.run",
        lambda *a, **k: __import__("types").SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="fatal: unable to access 'https://x-access-token:s3cr3t@github.com/o/r.git/': 403",
        ),
    )
    with pytest.raises(ValidationFailed) as err:
        container.proposals.decide("branch", "agent/leak", "accepted")
    assert "s3cr3t" not in str(err.value) and "x-access-token" not in str(err.value)


def test_pr_via_github_rest(container, monkeypatch, tmp_path):
    """gh нет — PR создаётся REST-запросом с токеном настроек (B-011)."""
    import types

    (tmp_path / ".git").mkdir()
    svc = container.proposals
    monkeypatch.setattr(type(svc), "_repo_root", lambda self: tmp_path, raising=False)
    monkeypatch.setattr(svc._settings, "github_token", "tok", raising=False)

    calls = []

    def fake_run(argv, **k):
        if argv[:3] == ["git", "remote", "get-url"]:
            return types.SimpleNamespace(returncode=0, stdout="https://github.com/x/learnos.git\n", stderr="")
        raise AssertionError(f"неожиданный subprocess-вызов: {argv}")

    monkeypatch.setattr("app.modules.proposals.service.subprocess.run", fake_run)

    def fake_post(url, **kw):
        calls.append(("post", url, kw.get("json"), kw.get("headers")))
        return types.SimpleNamespace(
            status_code=201, json=lambda: {"html_url": "https://github.com/o/r/pull/9"}
        )

    monkeypatch.setattr("app.modules.proposals.service.httpx.post", fake_post)

    url, note = svc._pr_via_api(tmp_path, "agent/fix")  # noqa: SLF001 — прямой вызов вместо gh
    assert url == "https://github.com/o/r/pull/9" and note is None
    _, url_called, body, headers = calls[0]
    assert "/repos/x/learnos/pulls" in url_called
    assert body["head"] == "agent/fix" and body["base"] == "main"
    assert headers["Authorization"] == "Bearer tok"


def test_pr_via_api_returns_reason(container, monkeypatch, tmp_path):
    """PR не создался — accept отдаёт причину, а не молчание (ревью B-011)."""
    import types

    (tmp_path / ".git").mkdir()
    svc = container.proposals
    monkeypatch.setattr(type(svc), "_repo_root", lambda self: tmp_path, raising=False)

    def fake_run(argv, **k):
        if argv[:3] == ["git", "remote", "get-url"]:
            return types.SimpleNamespace(returncode=0, stdout="https://github.com/x/learnos.git\n", stderr="")
        raise AssertionError(f"неожиданный subprocess-вызов: {argv}")

    monkeypatch.setattr("app.modules.proposals.service.subprocess.run", fake_run)

    # токена нет — причина, а не None
    monkeypatch.setattr(svc._settings, "github_token", "", raising=False)
    _, note = svc._pr_via_api(tmp_path, "agent/fix")  # noqa: SLF001
    assert note and "LEARNOS_GITHUB_TOKEN" in note

    # GitHub отклонил токен — код в причине
    monkeypatch.setattr(svc._settings, "github_token", "tok", raising=False)
    monkeypatch.setattr(
        "app.modules.proposals.service.httpx.post",
        lambda *a, **k: types.SimpleNamespace(status_code=403, json=lambda: {}),
    )
    _, note = svc._pr_via_api(tmp_path, "agent/fix")  # noqa: SLF001
    assert note and "403" in note

    # сеть недоступна — причина про прокси
    def no_net(*a, **k):
        import httpx

        raise httpx.ConnectError("refused")

    monkeypatch.setattr("app.modules.proposals.service.httpx.post", no_net)
    _, note = svc._pr_via_api(tmp_path, "agent/fix")  # noqa: SLF001
    assert note and "прокси" in note


def test_proposals_only_agent_tasks(container, monkeypatch, tmp_path):
    """«Предложения» — только задачи агентов: author: agent или from: ревизия кода (B-011)."""
    tasks_dir = tmp_path / "task_ai" / "tasks"
    tasks_dir.mkdir(parents=True)
    files = {
        "T-910-agent.md": (
            "---\nid: T-910\ntitle: Новая агентская\nstatus: idea\nauthor: agent\nfrom: x\n---\n"
        ),
        "T-911-old-agent.md": (
            "---\nid: T-911\ntitle: Старая агентская\nstatus: idea\nfrom: ревизия кода (auditor)\n---\n"
        ),
        "T-912-human.md": "---\nid: T-912\ntitle: Бэклог человека\nstatus: idea\nfrom: этап 8\n---\n",
    }
    for name, text in files.items():
        (tasks_dir / name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(type(container.proposals), "_repo_root", lambda self: tmp_path, raising=False)

    out = container.proposals.list()
    ids = [t["id"] for t in out["tasks"]]
    assert ids == ["T-910", "T-911"]


def test_proposals_data_tasks(container, monkeypatch, tmp_path):
    """Задачи из data (прод, read-only репо) видны с текстом; accept отдаёт текст (B-011)."""
    (tmp_path / "task_ai" / "tasks").mkdir(parents=True)
    data_dir = container.proposals._settings.data_dir / "proposals" / "tasks"  # noqa: SLF001
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "T-AGENT-2026-11-12-smoke.md").write_text(
        "---\nid: T-AGENT-2026-11-12-smoke\ntitle: Дымовая\nstatus: idea\nauthor: agent\n"
        "from: ревизия кода (auditor)\n---\n\n## Что нужно\n\nпроверить",
        encoding="utf-8",
    )
    monkeypatch.setattr(type(container.proposals), "_repo_root", lambda self: tmp_path, raising=False)

    out = container.proposals.list()
    data_tasks = [t for t in out["tasks"] if t.get("source") == "data"]
    assert len(data_tasks) == 1 and "## Что нужно" in data_tasks[0]["text"]

    accepted = container.proposals.decide("task", "T-AGENT-2026-11-12-smoke", "accepted")
    assert "## Что нужно" in accepted.get("task_text", "")


def test_create_task_file_fallback_to_data(container, monkeypatch, tmp_path):
    """Read-only git-дерево: задача агента уходит в data/proposals/tasks (B-011)."""
    import pathlib

    tasks_dir = tmp_path / "task_ai" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    rev = container.revision
    monkeypatch.setattr(type(rev), "_root", lambda self: tmp_path, raising=False)

    real_write = pathlib.Path.write_text

    def ro_write(self, data, encoding=None, errors=None, newline=None):
        if self.parent == tasks_dir:
            raise OSError(30, "Read-only file system")
        return real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(pathlib.Path, "write_text", ro_write)

    out = rev.create_task_file("Дымовая задача прод", "тело")
    assert out["location"] == "data"
    assert out["task_id"].startswith("T-AGENT-")
    assert out["file"].startswith("data/proposals/tasks/")
    text = rev._settings.data_dir.joinpath(*out["file"].split("/")[1:]).read_text(encoding="utf-8")  # noqa: SLF001
    assert "author: agent" in text and "status: idea" in text


def test_decide_route_accepts_slashed_branch_ref(client):
    """Маршрут decide принимает ветку со слэшем agent/x: ref:path (B-011).

    Обычный сегмент пути не матчит «agent/b011-accept-smoke» — accept ветки
    из UI падал 404 ещё до push.
    """
    res = client.post(
        "/api/proposals/branch/agent/b011-smoke/decide",
        json={"decision": "rejected"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "branch" and body["ref"] == "agent/b011-smoke"

    # решение скрыло ветку из «нерешённых» — список не падает
    assert client.get("/api/proposals").status_code == 200
