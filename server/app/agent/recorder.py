"""Запись трейсов запусков агентов в таблицу agent_runs."""

from ..kernel.clock import SystemClock, now_iso
from ..kernel.db import UnitOfWorkFactory


class DbRunRecorder:
    """Реализация RunRecorder на SQLite (см. ТЗ 02 «Наблюдаемость»)."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow
        self._clock = SystemClock()

    def record(
        self,
        *,
        agent: str,
        provider: str,
        model: str,
        conversation_uid: str | None,
        status: str,
        steps: int,
        tool_calls: int,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        error: str | None,
        parent_run_id: int | None = None,
    ) -> int:
        from .infra_tables import agent_runs_table

        del parent_run_id  # отдельная колонка пока не ведётся
        with self._uow() as uow:
            return int(
                uow.session.execute(
                    agent_runs_table.insert().values(
                        agent=agent,
                        provider=provider,
                        model=model,
                        conversation_uid=conversation_uid,
                        status=status,
                        steps=steps,
                        tool_calls=tool_calls,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        duration_ms=duration_ms,
                        error=error[:500] if error else None,
                        created_at=now_iso(self._clock),
                    )
                ).inserted_primary_key[0]
            )
