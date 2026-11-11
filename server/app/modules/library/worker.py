"""Воркер фоновых jobs: одна asyncio-задача, обрабатывает очередь по одной."""

import asyncio
import logging

import anyio

from ...kernel.clock import SystemClock, now_iso

log = logging.getLogger("learnos.worker")


class JobWorker:
    """Читает jobs из БД, выполняет последовательно; падение job не роняет воркер."""

    def __init__(self, library, runtime=None, extra_handlers: dict | None = None) -> None:
        self._library = library
        self._runtime = runtime
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.clock = SystemClock()
        # сторонние kinds (например search_embed, B-008): kind → callable(job) -> dict
        self._extra_handlers: dict = dict(extra_handlers or {})

    def register_handler(self, kind: str, handler) -> None:
        """Зарегистрировать обработчик чужого kind jobs (B-008: векторная индексация)."""
        self._extra_handlers[kind] = handler

    def enqueue(self, kind: str, target: str | None, total: int = 1) -> int:
        """Поставить job в очередь (без дедупликации — события редкие)."""
        from ...kernel.clock import now_iso
        from .infra.tables import jobs

        def _insert(uow):
            return int(
                uow.session.execute(
                    jobs.insert().values(
                        kind=kind,
                        target=target,
                        status="queued",
                        total=total,
                        created_at=now_iso(self.clock),
                        updated_at=now_iso(self.clock),
                    )
                ).inserted_primary_key[0]
            )

        with self._library._uow() as uow:  # noqa: SLF001
            return _insert(uow)

    async def start(self) -> None:
        """Запустить цикл воркера в фоне; до цикла — разбор залипших jobs (R-10)."""
        self._stop = asyncio.Event()
        try:
            recovered = await anyio.to_thread.run_sync(self._library.recover_stuck_jobs)
            if recovered.get("recovered_jobs"):
                log.warning("recovery: %s job(s) вернулись из running в failed", recovered["recovered_jobs"])
        except Exception:  # noqa: BLE001 — recovery не должен блокировать старт
            log.exception("recovery залепленных jobs не удался")
        self._task = asyncio.create_task(self._loop(), name="learnos-job-worker")

    async def stop(self) -> None:
        """Остановить воркер."""
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    @property
    def running(self) -> bool:
        """Воркер жив?"""
        return self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            job = await anyio.to_thread.run_sync(self._take_next)
            if job is None:
                await asyncio.sleep(1.5)
                continue
            log.info("job %s %s → running", job["id"], job["kind"])
            handler = self._extra_handlers.get(job["kind"])
            try:
                if handler is not None:
                    result = await anyio.to_thread.run_sync(handler, job)
                    await anyio.to_thread.run_sync(self._finish, job, result)
                    log.info("job %s done: %s", job["id"], result)
                else:
                    result = await anyio.to_thread.run_sync(self._library.run_job, job)
                    log.info("job %s done: %s", job["id"], result)
            except Exception:  # noqa: BLE001 — воркер не должен умирать
                log.exception("job %s failed", job["id"])
                await anyio.to_thread.run_sync(self._fail, job)

    def _take_next(self) -> dict | None:
        from sqlalchemy import select, update

        from .infra.tables import jobs

        # берём следующий queued job атомарно (status → running)
        def _fetch(uow):
            row = uow.session.execute(
                select(jobs).where(jobs.c.status == "queued").order_by(jobs.c.id)
            ).first()
            if row is None:
                return None
            uow.session.execute(
                update(jobs)
                .where(jobs.c.id == row.id)
                .values(status="running", updated_at=now_iso(self.clock))
            )
            return {
                "id": row.id,
                "kind": row.kind,
                "target": row.target,
                "status": "running",
                "progress": row.progress,
                "total": row.total,
                "message": row.message,
                "error": row.error,
            }

        with self._library._uow() as uow:  # noqa: SLF001
            return _fetch(uow)

    def _finish(self, job: dict, result: dict) -> None:
        """Завершить job стороннего хэндлера: done | skipped (embed недоступен)."""
        status = "skipped" if result.get("skipped") else "done"
        self._library.finish_job(job["id"], status, str(result)[:500])

    def _fail(self, job: dict) -> None:
        """Job → failed и его источник больше не «обрабатывается» (R-10)."""
        self._library.fail_stuck_job(job["id"], job.get("target"), "внутренняя ошибка воркера")
