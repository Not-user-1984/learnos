"""Сервис чата: разговоры, сообщения, запуск агента, SSE-события, отмена, сжатие истории."""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ...agent.runtime import AgentRuntime
from ...agent.spec import AgentContext, AgentSpec, CancellationToken
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import Clock, now_iso
from ...kernel.errors import NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
from ...llm.router import ModelRouter
from ...llm.types import Message
from .infra.sql_repo import ConversationRepository, MessageRepository
from .schemas import MODES

log = logging.getLogger("learnos.chat")


@dataclass(frozen=True, slots=True)
class SseEvent:
    """Одно событие SSE-протокола (см. ТЗ 04)."""

    event: str
    data: dict[str, Any]


AGENT_BY_MODE = {
    "free": "free_chat",
    "quick": "quick_reviewer",
    "session": "session_tutor",
    "tuning": "prompt_tuner",
}
SESSION_TOOLS = {"advance", "practice_step", "finish_session", "start_session"}


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
        self._ids = ids
        self._clock = clock
        self._settings = settings
        self._running: dict[str, CancellationToken] = {}
        self._previews: dict[str, list[dict]] = {}  # превью конспектов: conv → список драфтов

    # --- разговоры ---

    def create_conversation(
        self,
        mode: str = "free",
        activity: str | int | None = None,
        chapter: int | None = None,
        focus_block: str | None = None,
        title: str | None = None,
    ) -> dict:
        """Новый разговор в одном из режимов."""
        if mode not in MODES:
            raise ValidationFailed(f"режим должен быть одним из {sorted(MODES)}")
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
                created_at=now,
                updated_at=now,
            )
            return self._convs.get(uow.session, uid)

    def get_conversation(self, uid: str) -> dict:
        """Разговор + сообщения + сессия (если есть)."""
        with self._uow() as uow:
            conv = self._convs.get(uow.session, uid)
            conv["messages"] = self._msgs.list(uow.session, conv["id"])
            session = (
                self._learning.session_for_conversation(conv["id"]) if conv["mode"] == "session" else None
            )
            conv["session"] = session
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
            return self._convs.list(uow.session, mode=mode, q=q, activity_ids=activity_ids, chapter=chapter)

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

    async def stream_reply(self, uid: str, content: str) -> AsyncIterator[SseEvent]:
        """Сохранить сообщение пользователя и запустить агента; поток SSE-событий.

        Генерация продолжает работу при разрыве соединения: события копятся в task,
        ответ сохраняется в БД независимо от читателя.
        """
        conv = self.get_conversation(uid)
        now = now_iso(self._clock)
        with self._uow() as uow:
            user_msg_id = self._msgs.insert(
                uow.session,
                conversation_id=conv["id"],
                role="user",
                content=content,
                cards_json="[]",
                created_at=now,
            )
            self._convs.update(uow.session, conv["id"], updated_at=now)
        yield SseEvent("user_saved", {"message_id": user_msg_id})

        # сессия для режима session: создаётся при первом сообщении
        session = None
        if conv["mode"] == "session":
            session = self._learning.session_for_conversation(conv["id"])
            if session is None:
                session = self._create_session_for(conv)
            yield _session_event(session)

        agent_name = AGENT_BY_MODE.get(conv["mode"], "free_chat")
        spec: AgentSpec = self._agents.get(agent_name)
        # conv прочитан до вставки user-сообщения: добавляем его сами, иначе первый
        # запрос разговора уйдёт без единого user-сообщения (z.ai отвечает 1214)
        history = await self._build_history(conv) + [Message(role="user", content=content)]
        ctx = AgentContext(
            conversation_uid=uid,
            session_uid=session["session_uid"] if session else None,
            system_extra=self._context_block(conv, session),
            cancellation=self._running.get(uid),
        )
        if uid in self._running:
            raise ValidationFailed("для этого разговора уже идёт генерация")
        token = CancellationToken()
        self._running[uid] = token
        ctx.cancellation = token

        text_parts: list[str] = []
        cards: list[dict] = []
        assistant_id: int | None = None
        after_tools = False  # после tool-шага новый текст начинаем с абзаца
        try:
            async for ev in self._runtime.run(spec, ctx, history):
                if ev.type == "text":
                    piece = ev.text
                    if after_tools and text_parts and not text_parts[-1].endswith("\n"):
                        piece = "\n\n" + piece
                    after_tools = False
                    text_parts.append(piece)
                    yield SseEvent("delta", {"text": piece})
                elif ev.type == "tool_end":
                    after_tools = True
                    yield SseEvent(
                        "tool_end",
                        {"call_id": ev.call_id, "name": ev.name, "ok": ev.ok, "summary": ev.summary},
                    )
                    if conv["mode"] == "session" and ev.name in SESSION_TOOLS:
                        fresh = self._learning.session_for_conversation(conv["id"])
                        if fresh:
                            yield _session_event(fresh)
                elif ev.type == "tool_start":
                    yield SseEvent(
                        "tool_start",
                        {"call_id": ev.call_id, "name": ev.name, "args": ev.args, "label": ev.label},
                    )
                elif ev.type == "card":
                    cards.append(ev.card or {})
                    yield SseEvent("card", {"call_id": ev.call_id, "card": ev.card})
                elif ev.type == "error":
                    yield SseEvent("error", {"error": "agent_error", "message": ev.text})
            text = "".join(text_parts)
            if text or cards:
                with self._uow() as uow:
                    now2 = now_iso(self._clock)
                    assistant_id = self._msgs.insert(
                        uow.session,
                        conversation_id=conv["id"],
                        role="assistant",
                        content=text,
                        cards_json=json.dumps(cards, ensure_ascii=False),
                        created_at=now2,
                    )
                    self._convs.update(uow.session, conv["id"], updated_at=now2)
                if conv["title"] == "Новый разговор" and text:
                    new_title = await self._make_title(conv, text)
                    if new_title:
                        yield SseEvent("title", {"title": new_title})
            yield SseEvent("done", {"message_id": assistant_id})
        finally:
            self._running.pop(uid, None)

    def stop(self, uid: str) -> dict:
        """Прервать текущую генерацию разговора."""
        token = self._running.get(uid)
        if token is None:
            return {"ok": False, "note": "нет активной генерации"}
        token.cancel()
        return {"ok": True}

    # --- контекст ---

    async def _build_history(self, conv: dict) -> list[Message]:
        """История с бюджетом ~24k токенов; старая половина сжимается в summary."""
        all_msgs = [m for m in conv["messages"] if m["role"] in {"user", "assistant"} and m["content"]]
        budget_chars = int(self._settings.context_budget_tokens * 3.5)
        recent: list[dict] = []
        total = 0
        for m in reversed(all_msgs):
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

    def _context_block(self, conv: dict, session: dict | None) -> str:
        """Системный блок «Контекст»: профиль, источник, глава, состояние сессии, блок в фокусе."""
        parts = [f"Профиль пользователя:\n{self._profile.machines_brief()}", self._profile.learning_brief()]
        if conv.get("activity_id"):
            try:
                act = self._learning.get_activity(conv["activity_id"])
                src = self._library.get_source(act["source_id"])
                if src["kind"] == "video":
                    parts.append(
                        f"Активность: {act['title']} "
                        f"(видео, запись {act['cursor_chapter']}/{act['total_chapters']})"
                    )
                else:
                    parts.append(
                        f"Активность: {act['title']} "
                        f"(курсор на главе {act['cursor_chapter']}/{act['total_chapters']})"
                    )
                parts.append(self._source_brief(src))
                chapter_idx = conv.get("chapter_idx") or act["cursor_chapter"]
                chapters = [ch for ch in src.get("chapters", []) if ch["idx"] == chapter_idx]
                if src["kind"] == "video":
                    parts.append(
                        "Режим видео: весь транскрипт — одна запись (chapter=1). Прочитай его ЦЕЛИКОМ: "
                        "read_chapter(chapter=1, limit=24000, offset=…), листай offset, пока next_offset "
                        "не станет null. Разбирай видео как единое целое; не говори «глава» — только "
                        "«видео»/«транскрипт»."
                    )
                elif chapters:
                    ch = chapters[0]
                    kp = "; ".join(ch.get("key_points") or [])
                    parts.append(
                        f"Текущая глава {ch['idx']}. {ch['title']}: {ch.get('summary') or ''}\n"
                        f"Ключевые пункты: {kp}"
                    )
            except NotFound:
                pass
        elif conv.get("chapter_idx") is None and conv["mode"] in {"quick", "session"}:
            parts.append(
                "Источник не выбран — попроси пользователя выбрать источник/главу или предложи загрузить."
            )
        if session:
            parts.append(
                f"Состояние сессии: state={session['state']}; "
                f"разрешённые события: {', '.join(session['allowed_events'])}. "
                "Сессия привязана к разговору: вызывай advance/practice_step/finish_session БЕЗ session_id."
            )
        if conv.get("focus_block_uid"):
            try:
                b = self._knowledge.get_block(conv["focus_block_uid"])
                parts.append(
                    f"Блок в фокусе: {b.meta.title}\n{b.meta.summary}\n(Тело блока: {b.content[:1500]})"
                )
            except NotFound:
                pass
        return "\n\n".join(parts)

    @staticmethod
    def _source_brief(src: dict) -> str:
        if src["kind"] == "video":
            head = (src.get("chapters") or [{}])[0]
            return (
                f"Источник: {src['title']} (видео, YouTube; uid={src['uid']}) — используй только его\n"
                f"Транскрипт — одна запись (chapter=1). Обзор: {src.get('summary') or '—'}\n"
                f"Начало транскрипта: {(head.get('summary') or '')[:200] or '—'}"
            )
        toc = "\n".join(
            f"{ch['idx']}. {ch['title']} — {(ch.get('summary') or '')[:120]}"
            for ch in src.get("chapters", [])[:30]
        )
        return (
            f"Источник: {src['title']} ({src['kind']}, uid={src['uid']}) — используй только его\n"
            f"Обзор: {src.get('summary') or '—'}\nОглавление:\n{toc or '—'}"
        )

    def _create_session_for(self, conv: dict) -> dict:
        """Сессия из разговора: активность/глава из разговора, конфиг из профиля."""
        profile = self._profile.get()
        config = {
            "concepts": profile.learning.theory_concepts,
            "questions_per_block": profile.learning.questions_per_concept,
            "practice": profile.learning.practice_default,
            "minutes": profile.learning.session_minutes,
        }
        activity = self._learning.get_activity(conv["activity_id"]) if conv.get("activity_id") else None
        return self._learning.start_session(
            activity_ref=activity["id"] if activity else None,
            chapter_idx=conv.get("chapter_idx"),
            conversation_id=conv["id"],
            config=config,
        )

    async def _make_title(self, conv: dict, first_reply: str) -> str | None:
        """Авто-заголовок разговора (роль fast)."""
        try:
            provider, model = self._router.resolve("fast")
            from ...llm.types import LLMRequest

            resp = await provider.complete(
                model,
                LLMRequest(
                    messages=(
                        Message(
                            role="system",
                            content=(
                                "Придумай заголовок разговора по-русски, ≤ 60 символов, "
                                "без кавычек. Ответь только заголовком."
                            ),
                        ),
                        Message(
                            role="user",
                            content=(conv["messages"][-1]["content"] if conv.get("messages") else "")[:500]
                            + "\n---\n"
                            + first_reply[:500],
                        ),
                    )
                ),
            )
            title = resp.text.strip().strip('"«»')[:60]
            if title:
                with self._uow() as uow:
                    self._convs.update(uow.session, conv["id"], title=title, updated_at=now_iso(self._clock))
                return title
        except Exception:  # noqa: BLE001 — заголовок не критичен
            log.info("title_maker не сработал")
        return None

    # --- генерация блока из разговора (save_note без draft) ---

    def generate_block_draft(
        self,
        conversation_uid: str | None,
        kind: str,
        title_hint: str | None = None,
        instructions: str | None = None,
    ):
        """Драфт блока из переписки (block_writer); instructions — правки пользователя к драфту."""

        from ..knowledge.agents import block_writer
        from ..knowledge.service import _writer_out_to_draft

        if not conversation_uid:
            return None
        conv = self.get_conversation(conversation_uid)
        # разбор ассистента — главный материал конспекта: берём щедро, реплики пользователя — короче
        dialog = "\n".join(
            f"{m['role']}: {m['content'][:6000] if m['role'] == 'assistant' else m['content'][:1500]}"
            for m in conv.get("messages", [])
            if m["role"] in {"user", "assistant"}
        )
        if not dialog.strip():
            return None
        extra = [f"kind={kind}"]
        if title_hint:
            extra.append(f"Подсказка заголовка: {title_hint}")
        if instructions:
            extra.append(f"Правки пользователя к драфту (обязательны): {instructions}")
        source_line = self._draft_source_line(conv)
        if source_line:
            extra.append(source_line)
        ctx = AgentContext(conversation_uid=conversation_uid, system_extra="\n".join(extra))
        out = run_coro_sync(self._runtime.run_structured(block_writer, ctx, dialog))
        return _writer_out_to_draft(out, kind=kind)

    def _draft_source_line(self, conv: dict) -> str:
        """Строка «Источник: … (глава N)» для block_writer — привязка драфта к пройденному."""
        try:
            act = self._learning.get_activity(conv["activity_id"])
            src = self._library.get_source(act["source_id"])
            chapter = conv.get("chapter_idx") or act["cursor_chapter"]
            return f"Источник: {src['title']} ({src['kind']}, uid={src['uid']}), глава {chapter}"
        except (KeyError, NotFound):
            return ""

    # --- превью конспекта: драфт живёт на сервере, апрув идёт по preview_id ---

    def store_draft_preview(self, conversation_uid: str, draft) -> int:
        """Положить превью драфта, вернуть preview_id для save_note."""
        d = draft if isinstance(draft, dict) else _draft_to_plain(draft)
        history = self._previews.setdefault(conversation_uid, [])
        history.append(d)
        return len(history)

    def get_draft_preview(self, conversation_uid: str | None, preview_id: int) -> dict | None:
        """Превью по id (None — не найдено/протухло)."""
        if not conversation_uid:
            return None
        history = self._previews.get(conversation_uid) or []
        return history[preview_id - 1] if 0 < preview_id <= len(history) else None


def _session_event(session: dict) -> SseEvent:
    """SSE-событие session: state, allowed_events, прогресс."""
    transcript = session.get("transcript") or []
    progress = {
        "theory_done": sum(1 for t in transcript if t["event"] == "theory_done"),
        "questions_done": sum(1 for t in transcript if t["event"] == "ask"),
    }
    return SseEvent(
        "session",
        {"state": session["state"], "allowed_events": session["allowed_events"], "progress": progress},
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
