"""Запись трейсов запусков агентов в таблицу agent_runs."""

import datetime

from sqlalchemy import select

from ..kernel.clock import SystemClock, now_iso
from ..kernel.db import UnitOfWorkFactory
from .infra_tables import agent_runs_table

# живые запуски старше этого возраста считаем мусором от прошлых процессов
ACTIVE_RUN_MAX_AGE = datetime.timedelta(hours=2)
# «прервано недавно» — окно, за которым interrupted-запуски ещё показываются баннером
INTERRUPTED_WINDOW = datetime.timedelta(hours=24)


def _utcnow_naive() -> datetime.datetime:
    """«Сейчас» в UTC без таймзоны: все сравнения времени трейсов — в одном типе."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class DbRunRecorder:
    """RunRecorder на SQLite: строка запуска появляется в начале (id — для parent_run_id
    субагентов), агрегаты и статус дописываются в конце (см. ТЗ 02 «Наблюдаемость»)."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def start(
        self,
        *,
        agent: str,
        provider: str,
        model: str,
        conversation_uid: str | None,
        parent_run_id: int | None = None,
    ) -> int:
        with self._uow() as uow:
            return int(
                uow.session.execute(
                    agent_runs_table.insert().values(
                        agent=agent,
                        provider=provider,
                        model=model,
                        conversation_uid=conversation_uid,
                        status="running",
                        steps=0,
                        tool_calls=0,
                        input_tokens=0,
                        output_tokens=0,
                        duration_ms=0,
                        error=None,
                        parent_run_id=parent_run_id,
                        created_at=now_iso(SystemClock()),
                    )
                ).inserted_primary_key[0]
            )

    def progress(self, run_id: int, *, steps: int, tool_calls: int, current: str | None = None) -> None:
        """Живой прогресс выполнения: агрегаты и текущий инструмент пишутся
        инкрементально по ходу запуска (статус остаётся running до finish) —
        это то, что показывает бейдж «агент работает»."""
        with self._uow() as uow:
            uow.session.execute(
                agent_runs_table.update()
                .where(agent_runs_table.c.id == run_id, agent_runs_table.c.status == "running")
                .values(steps=steps, tool_calls=tool_calls, current_tool=current)
            )

    def finish(
        self,
        run_id: int,
        *,
        status: str,
        steps: int,
        tool_calls: int,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        error: str | None,
    ) -> None:
        with self._uow() as uow:
            uow.session.execute(
                agent_runs_table.update()
                .where(agent_runs_table.c.id == run_id)
                .values(
                    status=status,
                    steps=steps,
                    tool_calls=tool_calls,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    error=error[:500] if error else None,
                )
            )

    # --- состояние запусков (правда о работе агента для клиента) ---

    def interrupt_stale_running(self) -> int:
        """Хук старта процесса: зависшие running (перезапуск убил генерацию) → interrupted."""
        with self._uow() as uow:
            result = uow.session.execute(
                agent_runs_table.update()
                .where(agent_runs_table.c.status == "running")
                .values(status="interrupted", error="процесс перезапущен")
            )
            return int(result.rowcount or 0)

    def active_runs(self, conversation_uid: str) -> list[dict]:
        """Живые запуски разговора (root и субагенты несут один conversation_uid):
        status=running и возраст меньше ACTIVE_RUN_MAX_AGE."""
        rows = self._runs_of_conversation(conversation_uid, {"running"})
        cutoff = _utcnow_naive() - ACTIVE_RUN_MAX_AGE
        return [
            {
                "agent": r.agent,
                "steps": r.steps,
                "tool_calls": r.tool_calls,
                "current": r.current_tool,
                "started_at": r.created_at,
            }
            for r in rows
            if self._parse_iso(r.created_at) >= cutoff
        ]

    def has_recent_interrupted(self, conversation_uid: str) -> bool:
        """Есть ли у разговора свежие interrupted-запуски (окно INTERRUPTED_WINDOW)."""
        rows = self._runs_of_conversation(conversation_uid, {"interrupted"})
        cutoff = _utcnow_naive() - INTERRUPTED_WINDOW
        return any(self._parse_iso(r.created_at) >= cutoff for r in rows)

    def _runs_of_conversation(self, conversation_uid: str, statuses: set[str]):
        with self._uow() as uow:
            return uow.session.execute(
                select(agent_runs_table)
                .where(
                    agent_runs_table.c.conversation_uid == conversation_uid,
                    agent_runs_table.c.status.in_(statuses),
                )
                .order_by(agent_runs_table.c.id)
            ).all()

    @staticmethod
    def _parse_iso(value: str) -> datetime.datetime:
        """ISO-строка → naive UTC: aware-метки переводятся в UTC и теряют tzinfo,
        чтобы сравнения с «сейчас» не смешивали aware и naive (TypeError — и фильтр
        живых запусков молча терялся бы выше по стеку)."""
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.UTC).replace(tzinfo=None)
        return dt
