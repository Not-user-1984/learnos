"""Сервис чата: разговоры, сообщения, запуск агента, SSE-события, отмена, сжатие истории."""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ...agent.runtime import AgentRuntime
from ...agent.spec import CancellationToken
from ...kernel.clock import Clock, now_iso
from ...kernel.errors import Conflict, ValidationFailed
from ...kernel.ids import IdGenerator
from ...llm.router import ModelRouter
from ...llm.types import Message
from .cards import ensure_card_ids
from .infra.sql_repo import ConversationRepository, MessageRepository
from .schemas import INTENTS, MODES
from .usecases.scenarios import (  # реэкспорт для совместимости (тесты/легаси)
    AGENT_BY_MODE,
    INTENT_AGENT,
    INTENT_DIRECTIVES,
    RESEARCH_DIRECTIVE,
    RESEARCH_MAX_STEPS,
)
from .usecases.scenarios import (
    valid_mode as _valid_mode,
)

__all__ = ["AGENT_BY_MODE", "INTENT_DIRECTIVES", "INTENT_AGENT", "RESEARCH_DIRECTIVE", "RESEARCH_MAX_STEPS"]

log = logging.getLogger("learnos.chat")


@dataclass(frozen=True, slots=True)
class SseEvent:
    """Одно событие SSE-протокола (см. ТЗ 04)."""

    event: str
    data: dict[str, Any]


class ChatService:
    """Use-cases чата: создать разговор, отправить сообщение (агент отвечает потоком), стоп."""

    def __init__(
        self,
        uow,
        conversations: ConversationRepository,
        messages: MessageRepository,
        runtime: AgentRuntime,
        registry,
        tools,
        router: ModelRouter,
        learning,
        library,
        knowledge,
        profile,
        recorder,
        ids: IdGenerator,
        clock: Clock,
        settings,
    ) -> None:
        self._uow = uow
        self._convs = conversations
        self._msgs = messages
        self._runtime = runtime
        self._agents = registry
        self._tools = tools
        self._router = router
        self._learning = learning
        self._library = library
        self._knowledge = knowledge
        self._profile = profile
        self._recorder = recorder  # agent_runs: живые запуски и следы прерываний
        self._ids = ids
        self._clock = clock
        self._settings = settings
        self._running: dict[str, CancellationToken] = {}
        self._previews: dict[str, list[dict]] = {}  # превью конспектов: conv → список драфтов
        # use-cases (B-009): сервис — фасад, поведение не изменилось
        from .usecases.context import ContextBuilder
        from .usecases.drafts import DraftUseCases
        from .usecases.history import HistoryBuilder
        from .usecases.stream import ReplyStreamer
        from .usecases.titles import TitleMaker

        self._context_uc = ContextBuilder(self)
        self._history_uc = HistoryBuilder(self)
        self._titles_uc = TitleMaker(self)
        self._drafts_uc = DraftUseCases(self)
        self._stream_uc = ReplyStreamer(self)

    # --- разговоры ---

    def create_conversation(
        self,
        mode: str = "root",
        activity: str | int | None = None,
        chapter: int | None = None,
        focus_block: str | None = None,
        title: str | None = None,
        context_ref: str | None = None,
    ) -> dict:
        """Новый разговор в одном из режимов (кастомные агенты — mode='agent:<имя>')."""
        if not _valid_mode(self._agents, mode):
            raise ValidationFailed(f"режим должен быть одним из {sorted(MODES)} или agent:<имя кастомного>")
        uid = self._ids.new("cnv")
        now = now_iso(self._clock)
        with self._uow() as uow:
            activity_id = None
            if activity is not None:
                act = self._learning.get_activity(activity)
                activity_id = act["id"]
            self._convs.insert(
                uow.session,
                uid=uid,
                title=title or "Новый разговор",
                mode=mode,
                activity_id=activity_id,
                chapter_idx=chapter,
                focus_block_uid=focus_block,
                context_ref=context_ref,
                created_at=now,
                updated_at=now,
            )
            return self._convs.get(uow.session, uid)

    def chapter_conversation(self, source_ref: str | int, chapter_idx: int) -> dict:
        """Разговор главы источника (get-or-create, split-view B-006): повторное
        открытие главы продолжает тот же разговор, история не размножается."""
        src = self._library.get_source(source_ref)
        context_ref = f"{src['uid']}:{chapter_idx}"
        with self._uow() as uow:
            existing = self._convs.find_by_context_ref(uow.session, context_ref)
            if existing is not None:
                return existing
        act = self._learning.start_activity(src["uid"])
        ch = next((c for c in src.get("chapters", []) if c["idx"] == chapter_idx), None)
        title = f"Разбор: {ch['title'] if ch else src['title']}"[:80]
        return self.create_conversation(
            activity=act["uid"], chapter=chapter_idx, title=title, context_ref=context_ref
        )

    def get_conversation(self, uid: str) -> dict:
        """Разговор: сообщения, сессия, прогресс разбора, сценарий, состояние агента."""
        with self._uow() as uow:
            conv = self._convs.get(uow.session, uid)
            conv["messages"] = [
                {**m, "cards": ensure_card_ids(m["id"], m["cards"])}
                for m in self._msgs.list(uow.session, conv["id"])
            ]
            conv["session"] = self._learning.session_for_conversation(conv["id"])
            conv["review_progress"] = self._review_progress(conv)
            conv["scenario"] = self._scenario(conv, self._activity_source_kind(conv))
            conv["agent_state"] = self._agent_state(uid, conv["messages"])
            return conv

    def list_conversations(
        self,
        mode: str | None = None,
        q: str | None = None,
        source: str | int | None = None,
        chapter: int | None = None,
    ) -> list[dict]:
        """Список разговоров; source+chapter — история разговоров по главе источника."""
        activity_ids = None
        if source is not None:
            activity_ids = self._learning.activity_ids_for_source(source)
        with self._uow() as uow:
            convs = self._convs.list(uow.session, mode=mode, q=q, activity_ids=activity_ids, chapter=chapter)
            for c in convs:
                c["scenario"] = self._scenario(c)
            return convs

    def activity_id_for_conversation(self, uid: str) -> int | None:
        """Активность разговора (для mark_chapter_done из quick-разбора)."""
        with self._uow() as uow:
            return self._convs.get(uow.session, uid).get("activity_id")

    def conversation_uid(self, conversation_id: int) -> str | None:
        """uid разговора по id (для дашборда «Сегодня», B-005)."""
        with self._uow() as uow:
            return self._convs.get_by_id(uow.session, conversation_id)["uid"]

    def detach_activities(self, activity_ids: list[int]) -> None:
        """Отвязать разговоры от активностей источника (при удалении источника история остаётся)."""
        if not activity_ids:
            return
        with self._uow() as uow:
            self._convs.detach_activities(uow.session, activity_ids)

    def patch_conversation(self, uid: str, title: str | None = None) -> dict:
        """Переименовать разговор."""
        with self._uow() as uow:
            conv = self._convs.get(uow.session, uid)
            self._convs.update(
                uow.session, conv["id"], title=title or conv["title"], updated_at=now_iso(self._clock)
            )
            return self._convs.get(uow.session, uid)

    def delete_conversation(self, uid: str) -> dict:
        """Удалить разговор и сообщения (блоки не трогаем)."""
        with self._uow() as uow:
            conv = self._convs.get(uow.session, uid)
            self._convs.delete(uow.session, conv["id"])
        return {"ok": True, "deleted": uid}

    # --- отправка сообщения (SSE) ---

    async def stream_reply(
        self,
        uid: str,
        content: str,
        research: bool = False,
        attachments: list[str] | None = None,
        intent: str | None = None,
    ) -> AsyncIterator[SseEvent]:
        """Сохранить сообщение пользователя и запустить агента; поток SSE-событий.

        Генерация продолжает работу при разрыве соединения: события копятся в task,
        ответ сохраняется в БД независимо от читателя.
        research=True — сообщение запускает ресёрч-цикл: директива уходит агенту
        в system_extra (пользователь видит только свою тему), лимит шагов выше.
        attachments — uid источников (PDF), загруженных до отправки: заметка о них
        уходит агенту в system_extra, карточки-вложения — в user-сообщение.
        intent — сценарий входа (review/study/session/…): директива из
        INTENT_DIRECTIVES уходит в system_extra; «session» создаёт сессию,
        привязанную к разговору (как режим session).
        """
        if intent is not None and intent not in INTENTS:
            raise ValidationFailed(f"intent должен быть одним из {INTENTS}")
        # занятый разговор честно 409 ещё до стрима: сообщение не сохраняется
        # (раньше проверка жила в _reply_stream ПОСЛЕ вставки — дубли «Да» копились в истории)
        self.ensure_idle(uid)
        conv = self.get_conversation(uid)
        attach_cards, attach_note = self._resolve_attachments(attachments or [])
        now = now_iso(self._clock)
        with self._uow() as uow:
            user_msg_id = self._msgs.insert(
                uow.session,
                conversation_id=conv["id"],
                role="user",
                content=content,
                cards_json=json.dumps(attach_cards, ensure_ascii=False),
                created_at=now,
            )
            self._convs.update(uow.session, conv["id"], updated_at=now)
        yield SseEvent("user_saved", {"message_id": user_msg_id})

        # сессия: режим session создаёт её первым сообщением; интент «session» —
        # то же для root-разговора (кнопка «Сессия» у главы). Сессия, созданная
        # агентом по ходу (start_session), подтягивается ниже по tool_end.
        session = self._learning.session_for_conversation(conv["id"])
        if session is None and (conv["mode"] == "session" or intent == "session"):
            session = self._create_session_for(conv)
        # handoff: интент-сценарий передаёт разговор специалисту (review/session);
        # legасy-режимы (mode=quick/session) ведутся как раньше — без active_agent
        specialist = INTENT_AGENT.get(intent or "")
        if specialist and not conv.get("active_agent") and conv["mode"] in {"root", "free"}:
            with self._uow() as uow:
                self._convs.set_active_agent(uow.session, conv["id"], specialist)
            conv = {**conv, "active_agent": specialist}
            yield SseEvent("handoff", {"agent": specialist, "reason": f"интент {intent}"})
        if session:
            yield _session_event(session)

        # компактация (R-12): история переросла бюджет — старое уходит в summary
        compacted = await self.maybe_compact(conv)
        if compacted:
            conv = {**conv, **compacted}
        # conv прочитан до вставки user-сообщения: добавляем его сами, иначе первый
        # запрос разговора уйдёт без единого user-сообщения (z.ai отвечает 1214)
        history = await self._build_history(conv) + [Message(role="user", content=content)]
        extra_notes = []
        if intent:
            extra_notes.append(INTENT_DIRECTIVES[intent])
        if attach_note:
            extra_notes.append(attach_note)
        async for ev in self._reply_stream(conv, session, content, history, extra_notes, research=research):
            yield ev

    def resume(self, uid: str) -> AsyncIterator[SseEvent]:
        """Дописать ответ после сбоя: генерация заново по последнему user-сообщению.

        User-сообщение не дублируется — оно уже в истории. Проверки конфликта
        бросаются до первого события (клиент получает 409, а не SSE-error) и
        повторяются в потоке на случай гонки. Ресёрч-флаг и интент исходного
        сообщения не восстанавливаются: это перезапуск ответа, не реплей.
        """
        conv = self.get_conversation(uid)
        self._check_resume(conv)
        return self._resume_stream(conv)

    def _check_resume(self, conv: dict) -> None:
        last = conv["messages"][-1] if conv["messages"] else None
        if last is None or last["role"] != "user":
            raise Conflict("нет сообщения без ответа — продолжать нечего")
        self.ensure_idle(conv["uid"])

    def handoff_conversation(self, uid: str, agent: str) -> None:
        """Сменить агента, ведущего разговор (интент-сценарий или инструмент handoff)."""
        conv = self.get_conversation(uid)
        with self._uow() as uow:
            self._convs.set_active_agent(uow.session, conv["id"], agent)

    def ensure_idle(self, uid: str) -> None:
        """Разговор не генерирует ответ сейчас; иначе 409 — пользователь ждёт,
        а не получает тихий отказ с дублем сообщения в истории.

        Роут зовёт до открытия SSE-стрима (клиент видит HTTP 409 с пояснением),
        stream_reply повторяет проверку как вторую линию от гонки."""
        if uid in self._running or self._recorder.active_runs(uid):
            raise Conflict("агент уже работает — дождись ответа или останови его")

    async def _resume_stream(self, conv: dict) -> AsyncIterator[SseEvent]:
        self._check_resume(conv)
        last_user = next(m for m in reversed(conv["messages"]) if m["role"] == "user")
        session = self._learning.session_for_conversation(conv["id"])
        if session:
            yield _session_event(session)
        # история уже заканчивается незакрытым user-сообщением
        history = await self._build_history(conv)
        async for ev in self._reply_stream(conv, session, last_user["content"], history, []):
            yield ev

    async def _reply_stream(self, conv, session, content, history, extra_notes, research=False):
        """Общий цикл генерации (usecases/stream.py, B-009)."""
        async for ev in self._stream_uc._reply_stream(  # noqa: SLF001
            conv, session, content, history, extra_notes, research=research
        ):
            yield ev

    def _agent_state(self, uid: str, messages: list[dict]) -> dict:
        """Правда о генерации для клиента: агент работает / генерация прервана.

        working — есть живые запуски (root и субагенты несут conversation_uid запуска);
        interrupted — последнее user-сообщение без ответа и есть свежие следы
        прерванных запусков (рестарт процесса помечает их на старте).
        """
        runs = self._recorder.active_runs(uid)
        working = bool(runs)
        last = messages[-1] if messages else None
        interrupted = (
            not working
            and last is not None
            and last["role"] == "user"
            and self._recorder.has_recent_interrupted(uid)
        )
        return {"working": working, "runs": runs, "interrupted": interrupted}

    def stop(self, uid: str) -> dict:
        """Прервать текущую генерацию разговора."""
        token = self._running.get(uid)
        if token is None:
            return {"ok": False, "note": "нет активной генерации"}
        token.cancel()
        return {"ok": True}

    # --- контекст ---

    def _resolve_attachments(self, source_uids: list[str]) -> tuple[list[dict], str]:
        """Вложения-источники → карточки для user-сообщения + заметка агенту.

        PDF загружен до отправки сообщения (upload_pdf), агент оперирует готовым uid.
        Источник не найден (удалён в другом окне) — NotFound, сообщение не отправляется.
        """
        cards: list[dict] = []
        lines: list[str] = []
        for source_uid in source_uids:
            src = self._library.get_source(source_uid)
            cards.append({"type": "attachment", "title": src["title"], "source_uid": src["uid"]})
            lines.append(
                f"Пользователь приложил PDF «{src['title']}» (источник uid={src['uid']}). "
                "Доступные действия: process_source — нарежет книгу на главы; после обработки — "
                "list_chapters/read_chapter, быстрый разбор — run_agent('quick_reviewer') или сам."
            )
        note = ("Вложения сообщения:\n" + "\n".join(lines)) if lines else ""
        return cards, note

    # --- история LLM (перенесено в usecases/history.py, B-009) ---

    async def _build_history(self, conv: dict):
        return await self._history_uc._build_history(conv)  # noqa: SLF001

    async def maybe_compact(self, conv: dict) -> dict:
        return await self._history_uc.maybe_compact(conv)  # noqa: SLF001

    # --- контекст разговора (перенесено в usecases/context.py, B-009) ---

    def _activity_source_kind(self, conv: dict) -> str | None:
        return self._context_uc._activity_source_kind(conv)  # noqa: SLF001

    def _review_progress(self, conv: dict) -> dict | None:
        return self._context_uc._review_progress(conv)  # noqa: SLF001

    def _scenario(self, conv: dict, src_kind: str | None = None) -> str:
        return self._context_uc._scenario(conv, src_kind)  # noqa: SLF001

    def _context_block(self, conv: dict, session: dict | None) -> str:
        return self._context_uc._context_block(conv, session)  # noqa: SLF001

    def _source_brief(self, src: dict) -> str:
        return self._context_uc._source_brief(src)  # noqa: SLF001

    def _create_session_for(self, conv: dict) -> dict:
        return self._context_uc._create_session_for(conv)  # noqa: SLF001

    async def _make_title(self, conv: dict, first_reply: str) -> str | None:
        """Авто-заголовок (usecases/titles, B-009)."""
        return await self._titles_uc._make_title(conv, first_reply)  # noqa: SLF001

    # --- драфты блоков (перенесено в usecases/drafts.py, B-009) ---

    def generate_block_draft(self, conversation_uid, kind, title_hint=None, instructions=None):
        """Драфт блока из переписки (порт knowledge.generate_from_dialog)."""
        return self._drafts_uc.generate_block_draft(conversation_uid, kind, title_hint, instructions)

    def store_draft_preview(self, conversation_uid: str, draft) -> int:
        """Положить превью драфта, вернуть preview_id."""
        return self._drafts_uc.store_draft_preview(conversation_uid, draft)

    def get_draft_preview(self, conversation_uid: str | None, preview_id: int) -> dict | None:
        """Превью по id (None — не найдено/протухло)."""
        return self._drafts_uc.get_draft_preview(conversation_uid, preview_id)


def _session_event(session: dict) -> SseEvent:
    """SSE-событие session: uid, state, глава, разрешённые события, прогресс."""
    transcript = session.get("transcript") or []
    progress = {
        "theory_done": sum(1 for t in transcript if t["event"] == "theory_done"),
        "questions_done": sum(1 for t in transcript if t["event"] == "ask"),
    }
    return SseEvent(
        "session",
        {
            "session_uid": session["session_uid"],
            "state": session["state"],
            "allowed_events": session["allowed_events"],
            "chapter_idx": session.get("chapter_idx"),
            "progress": progress,
        },
    )


def _draft_to_plain(draft) -> dict:
    """BlockDraft (domain) → plain dict: совместим с BlockDraftIn и карточкой превью."""
    return {
        "title": draft.title,
        "summary": draft.summary,
        "kind": draft.kind,
        "concepts": [{"term": c.term, "definition": c.definition} for c in draft.concepts],
        "theses": list(draft.theses),
        "my_examples": list(draft.my_examples),
        "mermaid": draft.mermaid,
        "practice": [
            {
                "machine": p.machine,
                "command": p.command,
                "explanation": p.explanation,
                "result": p.result,
            }
            for p in draft.practice
        ],
        "weak_spots": list(draft.weak_spots),
        "open_questions": list(draft.open_questions),
        "links": list(draft.links),
        "tags": list(draft.tags),
        "category_suggestion": draft.category_suggestion,
        "sources": [{"source": s.source, "chapter": s.chapter, "title": s.title} for s in draft.sources],
    }
