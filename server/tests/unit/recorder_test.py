"""BUG-005: окно ACTIVE_RUN_MAX_AGE в recorder и сравнение времени в одном типе (UTC naive)."""

import datetime

from sqlalchemy import text

from app.agent.recorder import ACTIVE_RUN_MAX_AGE


def _insert_run(container, uid: str, *, created_at: str) -> None:
    with container.uow() as uow:
        uow.session.execute(
            text(
                "INSERT INTO agent_runs (agent, provider, model, conversation_uid, status, steps, "
                "tool_calls, input_tokens, output_tokens, duration_ms, error, parent_run_id, created_at) "
                "VALUES ('root', 'fake', 'fake-model', :uid, 'running', 3, 1, 0, 0, 0, NULL, NULL, :created)"
            ),
            {"uid": uid, "created": created_at},
        )


def test_active_runs_drops_stale_running(container):
    """Running-запуск возрастом за окном ACTIVE_RUN_MAX_AGE — не живой; свежий — живой."""
    uid = "cnv_stale_window"
    now = datetime.datetime.now(datetime.UTC)
    three_hours_ago = (now - ACTIVE_RUN_MAX_AGE - datetime.timedelta(hours=1)).isoformat()
    minute_ago = (now - datetime.timedelta(minutes=1)).isoformat()
    _insert_run(container, uid, created_at=three_hours_ago)
    _insert_run(container, uid, created_at=minute_ago)
    runs = container.run_recorder.active_runs(uid)
    assert [r["agent"] for r in runs] == ["root"]


def test_active_runs_tolerates_naive_created_at(container):
    """created_at без таймзоны (писался другим кодом/часами) не роняет сравнение:
    обе метки приводятся к naive UTC."""
    uid = "cnv_naive_stamp"
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    _insert_run(container, uid, created_at=(now - datetime.timedelta(hours=3)).isoformat(timespec="seconds"))
    fresh = (now - datetime.timedelta(minutes=2)).isoformat(timespec="seconds")
    _insert_run(container, uid, created_at=fresh)
    runs = container.run_recorder.active_runs(uid)
    assert [r["agent"] for r in runs] == ["root"]
