"""Запись трейсов запусков агентов в таблицу agent_runs."""

from ..kernel.clock import SystemClock, now_iso
from ..kernel.db import UnitOfWorkFactory
from .infra_tables import agent_runs_table


class DbRunRecorder:
    """RunRecorder на SQLite: строка запуска появляется в начале (id — для parent_run_id
    субагентов), агрегаты и статус дописываются в конце (см. ТЗ 02 «Наблюдаемость»)."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow
        self._clock = SystemClock()

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
                        created_at=now_iso(self._clock),
                    )
                ).inserted_primary_key[0]
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
