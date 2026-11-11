"""Сервис планировщика (B-010): тик, запуск джоб/агентов, дефолтные расписания."""

from __future__ import annotations

import logging

from ...agent.spec import AgentContext
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from .domain import cron_due

log = logging.getLogger("learnos.scheduler")

# дефолты: выключены (квота GLM), включаются в UI настроек
DEFAULTS = (
    ("auditor", "0 5 * * 1", "agent:auditor"),  # понедельник 05:00
    ("repo_scout", "0 6 * * 5", "agent:repo_scout"),  # пятница 06:00
    ("review_digest", "0 9 * * *", "job:review_digest"),  # ежедневно 09:00
)


class SchedulerService:
    """Тик раз в минуту: due → лок → запуск → статус."""

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        repo,
        runtime,
        registry,
        review,
        messenger,
        settings,
        clock: Clock | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._runtime = runtime
        self._registry = registry
        self._review = review
        self._messenger = messenger
        self._settings = settings
        from ...kernel.clock import SystemClock

        self._clock = clock or SystemClock()

    def ensure_defaults(self) -> None:
        with self._uow() as uow:
            for name, cron, action in DEFAULTS:
                self._repo.ensure(uow.session, name, cron, action)

    def list(self) -> list[dict]:
        with self._uow() as uow:
            rows = self._repo.all(uow.session)
        return [
            {
                "name": r["name"],
                "cron": r["cron"],
                "action": r["action"],
                "enabled": bool(r["enabled"]),
                "last_run_at": r["last_run_at"],
                "last_status": r["last_status"],
            }
            for r in rows
        ]

    def set_enabled(self, name: str, enabled: bool) -> dict:
        with self._uow() as uow:
            if self._repo.get(uow.session, name) is None:
                from ...kernel.errors import NotFound

                raise NotFound(f"расписание '{name}' не найдено")
            self._repo.set_enabled(uow.session, name, enabled)
        return {"ok": True, "name": name, "enabled": enabled}

    def tick(self) -> int:
        """Один тик планировщика: запустить всё дозревшее. Возвращает число запусков."""
        now = self._clock.now()
        due: list[dict] = []
        with self._uow() as uow:
            for row in self._repo.all(uow.session):
                if not row["enabled"]:
                    continue
                if row["last_status"] == "running":
                    continue  # уже идёт
                if cron_due(row["cron"], row["last_run_at"], now):
                    if self._repo.try_acquire(uow.session, row["id"], now_iso(self._clock)):
                        due.append(row)
        for row in due:
            self._run(row)
        return len(due)

    def run_now(self, name: str) -> dict:
        """Запустить задачу вручную (кнопка в UI), минуя cron."""
        with self._uow() as uow:
            row = self._repo.get(uow.session, name)
            from ...kernel.errors import NotFound

            if row is None:
                raise NotFound(f"расписание '{name}' не найдено")
            acquired = self._repo.try_acquire(uow.session, row["id"], now_iso(self._clock))
        if not acquired:
            return {"ok": False, "note": "уже выполняется"}
        self._run(row)
        return {"ok": True}

    def _run(self, row: dict) -> None:
        action = row["action"]
        try:
            if action == "job:review_digest":
                self._review_digest()
            elif action.startswith("agent:"):
                self._run_agent(action.split(":", 1)[1])
            else:
                raise ValueError(f"неизвестное действие {action}")
            status = "done"
        except Exception:  # noqa: BLE001 — статус в таблицу, тик живёт
            log.exception("schedule %s упал", row["name"])
            status = "error"
        with self._uow() as uow:
            self._repo.finish(uow.session, row["id"], status, now_iso(self._clock))

    def _review_digest(self) -> None:
        """Напоминание о повторениях в Telegram (при due_today > 0)."""
        stats = self._review.stats()
        if stats["due_today"] <= 0:
            return
        text = (
            f"Повторения: назрело {stats['due_today']}"
            f"{' · просрочено ' + str(stats['overdue']) if stats['overdue'] else ''}. "
            "Открой /review и проговори пару блоков."
        )
        self._messenger.send_text(text)

    async def _collect_agent(self, spec) -> None:
        async for _ in self._runtime.run(
            spec,
            AgentContext(system_extra="trigger=schedule: фоновый запуск по расписанию"),
            [],
        ):
            pass

    def _run_agent(self, name: str) -> None:
        """Запуск агента по расписанию: без разговора, метка trigger=schedule."""
        spec = self._registry.get(name)
        run_coro_sync(self._collect_agent(spec))
