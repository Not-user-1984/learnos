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
        "---\nid: T-901\ntitle: Идея скаута\nstatus: idea\nfrom: repo_scout\n---\n\nтело",
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
    assert pushes and pushes[0][0][1] == "push"
