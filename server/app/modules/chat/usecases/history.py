"""История для LLM: бюджет, ноты карточек, сжатие старого (B-009)."""

import logging

from sqlalchemy import update

from ....agent.spec import AgentContext
from ....kernel.asyncio_bridge import run_coro_sync
from ....llm.types import Message
from ..infra.tables import conversations as conversations_table
from .scenarios import history_notes as _history_notes

log = logging.getLogger("learnos.chat")


class HistoryBuilder:
    """Перенос из chat/service.py без изменения поведения."""

    def __init__(self, svc) -> None:
        self._svc = svc

    async def _build_history(self, conv: dict) -> list[Message]:
        """История для LLM с бюджетом; карточки и трасса инструментов не теряются (R-12).

        Бюджет в символах честен для кириллицы (~2.5 симв/токен, не 3.5): старое
        сжимается в conversations.summary (conversation_summarizer), в контексте —
        summary + последние сообщения.
        """
        enriched: list[dict] = []
        for m in conv["messages"]:
            if m["role"] not in {"user", "assistant"}:
                continue
            content = m["content"] or ""
            notes = _history_notes(m)
            if not content and not notes:
                continue
            enriched.append({"role": m["role"], "content": (content + notes).strip()})
        budget_chars = int(
            self._svc._settings.context_budget_tokens * self._svc._settings.context_chars_per_token
        )
        recent: list[dict] = []
        total = 0
        for m in reversed(enriched):
            if total + len(m["content"]) > budget_chars and recent:
                break
            recent.insert(0, m)
            total += len(m["content"])
        if conv.get("summary"):
            recent = [
                {"role": "assistant", "content": f"(Сжатая история разговора)\n{conv['summary']}"}
            ] + recent[-16:]
        return [
            Message(role="user" if m["role"] == "user" else "assistant", content=m["content"]) for m in recent
        ]

    async def maybe_compact(self, conv: dict) -> dict:
        """Сжать старую часть истории в conversations.summary, когда бюджет превышен (R-12).

        Возвращает словарь-обновление разговора (summary) или пустой. Сбой LLM
        не роняет чат: остаётся прежнее поведение (обрезка старого).
        """
        budget_chars = int(
            self._svc._settings.context_budget_tokens * self._svc._settings.context_chars_per_token
        )
        total = sum(len(m["content"] or "") for m in conv["messages"] if m["role"] in {"user", "assistant"})
        if total <= budget_chars:
            return {}
        older = [
            m for m in conv["messages"] if m["role"] in {"user", "assistant"} and (m["content"] or "").strip()
        ][:-16]
        if not older:
            return {}
        try:
            summary = await self._summarize_older(conv, older)
        except Exception:  # noqa: BLE001 — компактация не должна ломать ответ
            log.warning("conversation_summarizer не справился — история без сжатия", exc_info=True)
            return {}
        with self._svc._uow() as uow:
            uow.session.execute(
                update(conversations_table)
                .where(conversations_table.c.id == conv["id"])
                .values(summary=summary)
            )
        return {"summary": summary}

    async def _summarize_older(self, conv: dict, older: list[dict]) -> str:
        """fast-агент сжимает старые сообщения (с учётом прежнего summary)."""
        from ..agents import conversation_summarizer

        dialog = "\n".join(f"{m['role']}: {m['content']}" for m in older)[-16000:]
        base = f"Прежнее сжатие:\n{conv['summary']}" if conv.get("summary") else ""
        out = run_coro_sync(
            self._svc._runtime.run_structured(
                conversation_summarizer,
                AgentContext(conversation_uid=conv["uid"]),
                f"{base}\n\nДиалог:\n{dialog}".strip(),
            )
        )
        return out.summary
