"""Воркер фоновых jobs: одна asyncio-задача, обрабатывает очередь по одной."""

import asyncio
import logging

import anyio

from ...kernel.clock import SystemClock, now_iso

log = logging.getLogger("learnos.worker")


class JobWorker:
    """Читает jobs из БД, выполняет последовательно; падение job не роняет воркер."""

    def __init__(self, library, runtime=None) -> None:
        self._library = library
        self._runtime = runtime
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.clock = SystemClock()

    async def start(self) -> None:
        """Запустить цикл воркера в фоне."""
        self._stop = asyncio.Event()
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
            try:
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

    def _fail(self, job: dict) -> None:
        from sqlalchemy import update

        from .infra.tables import jobs

        with self._library._uow() as uow:  # noqa: SLF001
            uow.session.execute(
                update(jobs)
                .where(jobs.c.id == job["id"])
                .values(status="failed", error="внутренняя ошибка воркера", updated_at=now_iso(self.clock))
            )
