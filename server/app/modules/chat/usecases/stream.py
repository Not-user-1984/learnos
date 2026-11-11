"""SSE-цикл генерации ответа (B-009): контекст, агент, сохранение, карточки."""

import json
from collections.abc import AsyncIterator
from dataclasses import replace

from ....agent.spec import AgentContext, AgentSpec, CancellationToken
from ....kernel.clock import now_iso
from ....llm.types import Message
from ..agents import REVIEW_TOOLS, SESSION_TOOLS
from ..cards import DECISION_TYPES, build_options, ensure_card_ids, merge_decision
from ..domain import content_note
from ..service import (
    SseEvent,  # noqa: TC001
    _session_event,
)
from ..usecases.scenarios import (  # noqa: F401 — реэкспорт имён переноса
    INTENT_AGENT,  # noqa: F401
    RESEARCH_DIRECTIVE,
    RESEARCH_MAX_STEPS,
)
from ..usecases.scenarios import (
    agent_for_conversation as _agent_for_conversation,
)


class ReplyStreamer:
    """Перенос из chat/service.py без изменения поведения."""

    def __init__(self, svc) -> None:
        self._svc = svc

    async def _reply_stream(
        self,
        conv: dict,
        session: dict | None,
        content: str,
        history: list[Message],
        extra_notes: list[str],
        research: bool = False,
    ) -> AsyncIterator[SseEvent]:
        """Общий цикл генерации ответа (сообщение и resume): контекст, агент, сохранение."""
        uid = conv["uid"]
        agent_name = _agent_for_conversation(self._svc._agents, conv)
        spec: AgentSpec = self._svc._agents.get(agent_name)
        system_extra = self._svc._context_block(conv, session)  # noqa: SLF001
        # split-view (B-006): разговор привязан к главе — агент читает её по требованию
        # и для видео ссылается на таймкоды (кликабельны в панели)
        if conv.get("context_ref"):
            src_uid, _, ch_ref = conv["context_ref"].partition(":")
            system_extra = (
                f"{system_extra}\n\n"
                f"Разговор открыт рядом с главой {ch_ref} источника uid={src_uid}: материал получай "
                "read_chapter по этой главе (не пересказывай её целиком без нужды). Если источник — "
                "видео, указывай моменты таймкодами [мм:сс] (или [ч:мм:сс]) — в панели они кликабельны "
                "и перематывают плеер."
            ).strip()
        # претрекер контента: заметка о ссылках/ID в сообщении — агенту, без LLM
        for note in filter(None, [content_note(content), *extra_notes]):
            system_extra = f"{system_extra}\n\n{note}".strip()
        if research:
            spec = replace(spec, max_steps=RESEARCH_MAX_STEPS)
            system_extra = f"{system_extra}\n\n{RESEARCH_DIRECTIVE}".strip()
        self._svc.ensure_idle(uid)  # noqa: SLF001  # вторая линия от гонки: 409-проверка роута была до await'ов
        token = CancellationToken()
        self._svc._running[uid] = token
        ctx = AgentContext(
            conversation_uid=uid,
            session_uid=session["session_uid"] if session else None,
            system_extra=system_extra,
            cancellation=token,
        )

        text_parts: list[str] = []
        cards: list[dict] = []
        tool_trace: list[dict] = []
        assistant_id: int | None = None
        after_tools = False  # после tool-шага новый текст начинаем с абзаца
        try:
            async for ev in self._svc._runtime.run(spec, ctx, history):
                if ev.type == "text":
                    piece = ev.text
                    if after_tools and text_parts and not text_parts[-1].endswith("\n"):
                        piece = "\n\n" + piece
                    after_tools = False
                    text_parts.append(piece)
                    yield SseEvent("delta", {"text": piece})
                elif ev.type == "tool_end":
                    after_tools = True
                    # компактная трасса хода: чтозвали и чем кончилось (R-12) —
                    # сохраняется с ответом, подмешивается в историю LLM
                    tool_trace.append({"name": ev.name, "ok": ev.ok, "summary": (ev.summary or "")[:160]})
                    yield SseEvent(
                        "tool_end",
                        {"call_id": ev.call_id, "name": ev.name, "ok": ev.ok, "summary": ev.summary},
                    )
                    # сессия меняет состояние (или только создана агентом) — панель обновляется
                    if ev.name in SESSION_TOOLS:
                        fresh = self._svc._learning.session_for_conversation(conv["id"])
                        if fresh:
                            yield _session_event(fresh)
                    # курсор книги двигается (глава разобрана / сессия завершена) —
                    # статус-бар быстрого разбора обновляется
                    if ev.name in REVIEW_TOOLS:
                        progress = self._svc._review_progress(conv)  # noqa: SLF001
                        if progress:
                            yield SseEvent("review_progress", progress)
                elif ev.type == "tool_start":
                    yield SseEvent(
                        "tool_start",
                        {"call_id": ev.call_id, "name": ev.name, "args": ev.args, "label": ev.label},
                    )
                elif ev.type == "card":
                    # B-003: одна зона решений на ход — вторая decision-карточка
                    # вливается в первую (без дублей label), клиент заменяет её по index
                    card = dict(ev.card or {})
                    if card.get("type") in DECISION_TYPES:
                        card["options"] = build_options(card)
                    first_idx = next(
                        (i for i, c in enumerate(cards) if c.get("type") in DECISION_TYPES), None
                    )
                    if card.get("type") in DECISION_TYPES and first_idx is not None:
                        merge_decision(cards[first_idx], card)
                        yield SseEvent(
                            "card", {"call_id": ev.call_id, "card": cards[first_idx], "index": first_idx}
                        )
                    else:
                        cards.append(card)
                        yield SseEvent("card", {"call_id": ev.call_id, "card": card, "index": len(cards) - 1})
                elif ev.type == "error":
                    yield SseEvent("error", {"error": "agent_error", "message": ev.text})
            text = "".join(text_parts)
            if text or cards:
                with self._svc._uow() as uow:
                    now2 = now_iso(self._svc._clock)
                    assistant_id = self._svc._msgs.insert(
                        uow.session,
                        conversation_id=conv["id"],
                        role="assistant",
                        content=text,
                        cards_json=json.dumps(cards, ensure_ascii=False),
                        tool_calls_json=(
                            json.dumps(tool_trace[:12], ensure_ascii=False) if tool_trace else None
                        ),
                        created_at=now2,
                    )
                    # B-003: card_id нужен сразу — resolve возможен с первым же ответом
                    ensure_card_ids(assistant_id, cards)
                    self._svc._msgs.update_cards(uow.session, assistant_id, cards)
                    self._svc._convs.update(uow.session, conv["id"], updated_at=now2)
                if conv["title"] == "Новый разговор" and text:
                    new_title = await self._svc._make_title(conv, text)  # noqa: SLF001
                    if new_title:
                        yield SseEvent("title", {"title": new_title})
            yield SseEvent("done", {"message_id": assistant_id})
        finally:
            self._svc._running.pop(uid, None)
