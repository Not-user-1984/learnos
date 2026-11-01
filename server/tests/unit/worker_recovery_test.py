"""R-10: источник не залипает в processing после падения/рестарта воркера."""

import asyncio

from app.kernel.errors import Conflict


def _make_stuck(container) -> tuple[int, int, str]:
    """Источник в processing + job running (имитация убитого воркера)."""
    lib = container.library
    src = lib.add_source("video", "Видео", url="https://youtu.be/stuck123")
    lib.process_source(src["id"])
    # job реально уходит в running только в воркере; имитируем «убитый» воркер вручную
    from sqlalchemy import text, update

    from app.modules.library.infra.tables import jobs as jobs_t

    with lib._uow() as uow:  # noqa: SLF001
        row = uow.session.execute(
            text("SELECT id FROM jobs WHERE target = :t ORDER BY id DESC LIMIT 1"), {"t": src["uid"]}
        ).first()
        job_id = row[0]
        uow.session.execute(update(jobs_t).where(jobs_t.c.id == job_id).values(status="running"))
    return src["id"], job_id, src["uid"]


def test_recover_stuck_jobs_frees_source(container):
    """Старт сервиса: running-job → failed, источник processing → failed; повтор доступен (R-10)."""
    lib = container.library
    src_id, job_id, uid = _make_stuck(container)

    result = lib.recover_stuck_jobs()
    assert result["recovered_jobs"] >= 1

    src = lib.get_source(uid)
    assert src["status"] == "failed"  # больше не «обрабатывается» вечно
    job = lib.get_job(job_id)
    assert job["status"] == "failed"
    assert "перезапущен" in (job.get("error") or "")

    # process_source снова доступен без force (статус failed разрешает повтор)
    again = lib.process_source(src_id)
    assert again["ok"] is True


def test_process_conflict_while_processing_still_guarded(container):
    """Пока источник реально обрабатывается, повтор без force запрещён (как раньше)."""
    lib = container.library
    src = lib.add_source("video", "Видео2", url="https://youtu.be/stuck456")
    lib.process_source(src["id"])
    # воркер в тестах не стартовал, источник остался processing — как «в работе»
    try:
        lib.process_source(src["id"])
        raised = False
    except Conflict:
        raised = True
    assert raised


def test_worker_fail_updates_source_status(container):
    """Падение job в воркере помечает и job, и источник failed (R-10)."""
    lib = container.library
    src_id, job_id, uid = _make_stuck(container)
    container.job_worker._fail({"id": job_id, "target": uid})  # noqa: SLF001

    assert lib.get_job(job_id)["status"] == "failed"
    assert lib.get_source(uid)["status"] == "failed"


def test_worker_start_runs_recovery(container):
    """lifespace/start воркера вызывает recovery — залипший job разруливается сам (R-10)."""
    lib = container.library
    _src_id, job_id, _uid = _make_stuck(container)

    async def run() -> None:
        worker = container.job_worker
        await worker.start()
        await worker.stop()

    asyncio.run(run())
    assert lib.get_job(job_id)["status"] == "failed"
