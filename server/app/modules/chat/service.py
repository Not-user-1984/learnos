"""Сервис чата: разговоры, сообщения, запуск агента, SSE-события, отмена, сжатие истории."""

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import update

from ...agent.runtime import AgentRuntime
from ...agent.spec import AgentContext, AgentSpec, CancellationToken
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import Clock, now_iso
from ...kernel.errors import Conflict, NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
from ...llm.router import ModelRouter
from ...llm.types import Message
from .agents import REVIEW_TOOLS, SESSION_TOOLS
from .domain import content_note
from .infra.sql_repo import ConversationRepository, MessageRepository
from .infra.tables import conversations as conversations_table
from .schemas import INTENTS, MODES

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
    "root": "root",
}

# Ресёрч как состояние чата: директива видна только агенту (в system_extra),
# пользователь пишет тему как обычное сообщение.
RESEARCH_DIRECTIVE = (
    "Это сообщение запускает ресёрч-цикл по теме пользователя. Найди лучшие источники: "
    "официальные доки, статьи, видео. Ищи вширь (2–3 захода), остановись при повторах. "
    "Прогресс комментируй коротко: что нашёл, что читаешь. Итог — список кандидатов "
    "топ-3–5 с пояснением «почему этот». НИЧЕГО не добавляй в Библиотеку сам: покажи "
    "список и предложи добавление карточкой offer_action (в description — что именно "
    "добавишь). Согласие — «Да» на карточке или ответ с правкой списка («добавь только "
    "первые два», «добавь ещё видео»): добавь именно выбранные источники (kind=web "
    "через add_source + process_source; YouTube — kind=video) и подтверди, что добавил. "
    "Отказ — ничего не добавляй, продолжай по желаниям пользователя. "
    "Для научных/фундаментальных тем зови academic_search: ищет сразу по arXiv + OpenAlex + "
    "Semantic Scholar, у каждой статьи поле provider — упоминай источник находки. "
    "Доступен torrent_fetch (поиск книг/фильмов/музыки по трекерам): если тема — книга или "
    "пользователь просит медиа, покажи кандидатов и спроси, не скачать ли сразу; книги "
    "(cat=books) после загрузки сами попадают в Библиотеку с нарезкой глав."
)
RESEARCH_MAX_STEPS = 30  # цикл «поиск → чтение статей → добавление» не укладывается в дефолтные 12

# Сценарии единого входа (T-039): клиент передаёт код с первым сообщением,
# сервер собирает директиву агенту — видимый текст сообщения остаётся пользователю.
INTENT_DIRECTIVES = {
    "review": (
        "Сценарий «быстрый разбор»: источник и глава — в блоке «Контекст». Прочитай материал "
        "(read_chapter; видео — весь транскрипт, листай offset до конца) и покажи разбор "
        "карточкой show_chapter_review (главное 3–5 пунктов, ключевые понятия, что применимо "
        "пользователю, 1–2 вопроса на подумать; title — глава или название видео), текстом — "
        "2–3 строки сопровождения. Без сессии."
    ),
    "study": (
        "Сценарий «изучение источника»: пользователь начал с карты глав. Формат выбери сам — "
        "быстрый разбор текущей главы или сессия-урок (тогда start_session, сессия привяжется "
        "к разговору, и веди её шагами advance/practice_step/finish_session). После каждой главы "
        "решайте вместе кнопками offer_replies: дальше, подробнее или закрепить "
        "(mark_chapter_done по подтверждению)."
    ),
    "session": (
        "Сценарий «сессия-урок»: сессия уже создана и привязана к разговору (состояние — в "
        "«Контексте»). Веди урок сам: теория по первым понятиям коротко → вопросы фейнмана "
        "по одному → практика под железо из профиля → разбор; шаги — advance/practice_step/"
        "finish_session без session_id, итог — блок-урок."
    ),
    "quote": (
        "Сценарий «разбор фрагмента»: сообщение пользователя — выделенный фрагмент текущей "
        "главы. Объясни, что имеется в виду, сверься с текстом главы (read_chapter), поправь "
        "неточности понимания и свяжи фрагмент с ключевыми понятиями главы."
    ),
    "tune": (
        "Сценарий «настройка агента»: имя агента — в сообщении пользователя. Уточни вопросами, "
        "каким должно быть поведение, и предложи правку промпта карточкой propose_change("
        "kind='prompt', target=<агент>, …) — дифф увидит пользователь, применение по его кнопке."
    ),
    "reinforce": (
        "Сценарий «закрепление пройденного»: возьми очередь повторений (get_review_queue) и "
        "слабые места блоков (search/list_blocks), выбери 3–5 самых созревших или слабых и "
        "проводи короткое повторение по одному; каждый ответ оценивай answer_review."
    ),
}


# handoff (T-050 Э4): интент первого сообщения передаёт разговор специалисту,
# дальше он ведёт по своему промпту — директива больше не «одноразовая вставка»
INTENT_AGENT = {
    "review": "quick_reviewer",
    "session": "session_tutor",
}


def _history_notes(m: dict) -> str:
    """Компактное дополнение сообщения для контекста LLM: карточки и трасса инструментов (R-12).

    Пользователь их уже видел в UI; агент на следующих ходах должен помнить,
    что показал и чем закончились вызовы инструментов (сейчас — забывал).
    """
    notes: list[str] = []
    cards = m.get("cards") or []
    for c in cards[:4]:
        kind = c.get("type", "?")
        key = c.get("title") or c.get("task") or c.get("summary") or c.get("path") or ""
        note = f"[карточка {kind}" + (f": {str(key)[:90]}" if key else "") + "]"
        notes.append(note)
    trace = m.get("tool_calls") or []
    if trace:
        done = "; ".join(
            f"{t.get('name')}({'ок' if t.get('ok') else 'ошибка'}: {t.get('summary', '')[:60]})"
            for t in trace[:8]
        )
        notes.append(f"[инструменты: {done}]")
    return ("\n" + " ".join(notes)) if notes else ""


def _agent_for_conversation(registry, conv: dict) -> str:
    """Кто ведёт разговор: active_agent (handoff/интент), иначе режим (легаси)."""
    active = conv.get("active_agent")
    if active:
        try:
            registry.get(active)
            return active
        except KeyError:
            pass  # агента удалили — падаем обратно на режим, разговор не теряем
    return _agent_for_mode(registry, conv["mode"])


def _agent_for_mode(registry, mode: str) -> str:
    """Имя агента по режиму разговора: дефолтные режимы — из таблицы, agent:<name> — кастомный."""
    if mode.startswith("agent:"):
        name = mode.split(":", 1)[1]
        try:
            registry.get(name)
            return name
        except KeyError:
            return "free_chat"  # кастомного агента удалили — разговор не теряем
    return AGENT_BY_MODE.get(mode, "free_chat")


def _valid_mode(registry, mode: str) -> bool:
    if mode in MODES:
        return True
    if mode.startswith("agent:"):
        try:
            registry.get(mode.split(":", 1)[1])
            return True
        except KeyError:
            return False
    return False


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

    # --- разговоры ---

    def create_conversation(
        self,
        mode: str = "root",
        activity: str | int | None = None,
        chapter: int | None = None,
        focus_block: str | None = None,
        title: str | None = None,
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
                created_at=now,
                updated_at=now,
            )
            return self._convs.get(uow.session, uid)

    def get_conversation(self, uid: str) -> dict:
        """Разговор: сообщения, сессия, прогресс разбора, сценарий, состояние агента."""
        with self._uow() as uow:
            conv = self._convs.get(uow.session, uid)
            conv["messages"] = self._msgs.list(uow.session, conv["id"])
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
        agent_name = _agent_for_conversation(self._agents, conv)
        spec: AgentSpec = self._agents.get(agent_name)
        system_extra = self._context_block(conv, session)
        # претрекер контента: заметка о ссылках/ID в сообщении — агенту, без LLM
        for note in filter(None, [content_note(content), *extra_notes]):
            system_extra = f"{system_extra}\n\n{note}".strip()
        if research:
            spec = replace(spec, max_steps=RESEARCH_MAX_STEPS)
            system_extra = f"{system_extra}\n\n{RESEARCH_DIRECTIVE}".strip()
        self.ensure_idle(uid)  # вторая линия от гонки: 409-проверка роута была до await'ов
        token = CancellationToken()
        self._running[uid] = token
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
                    # компактная трасса хода: чтозвали и чем кончилось (R-12) —
                    # сохраняется с ответом, подмешивается в историю LLM
                    tool_trace.append({"name": ev.name, "ok": ev.ok, "summary": (ev.summary or "")[:160]})
                    yield SseEvent(
                        "tool_end",
                        {"call_id": ev.call_id, "name": ev.name, "ok": ev.ok, "summary": ev.summary},
                    )
                    # сессия меняет состояние (или только создана агентом) — панель обновляется
                    if ev.name in SESSION_TOOLS:
                        fresh = self._learning.session_for_conversation(conv["id"])
                        if fresh:
                            yield _session_event(fresh)
                    # курсор книги двигается (глава разобрана / сессия завершена) —
                    # статус-бар быстрого разбора обновляется
                    if ev.name in REVIEW_TOOLS:
                        progress = self._review_progress(conv)
                        if progress:
                            yield SseEvent("review_progress", progress)
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
                        tool_calls_json=(
                            json.dumps(tool_trace[:12], ensure_ascii=False) if tool_trace else None
                        ),
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
        budget_chars = int(self._settings.context_budget_tokens * self._settings.context_chars_per_token)
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
        budget_chars = int(self._settings.context_budget_tokens * self._settings.context_chars_per_token)
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
        with self._uow() as uow:
            uow.session.execute(
                update(conversations_table)
                .where(conversations_table.c.id == conv["id"])
                .values(summary=summary)
            )
        return {"summary": summary}

    async def _summarize_older(self, conv: dict, older: list[dict]) -> str:
        """fast-агент сжимает старые сообщения (с учётом прежнего summary)."""
        from .agents import conversation_summarizer

        dialog = "\n".join(f"{m['role']}: {m['content']}" for m in older)[-16000:]
        base = f"Прежнее сжатие:\n{conv['summary']}" if conv.get("summary") else ""
        out = run_coro_sync(
            self._runtime.run_structured(
                conversation_summarizer,
                AgentContext(conversation_uid=conv["uid"]),
                f"{base}\n\nДиалог:\n{dialog}".strip(),
            )
        )
        return out.summary

    def _activity_source_kind(self, conv: dict) -> str | None:
        """Тип источника активности разговора (для сценария «Разбор видео/материала»)."""
        if not conv.get("activity_id"):
            return None
        try:
            act = self._learning.get_activity(conv["activity_id"])
            return self._library.get_source(act["source_id"])["kind"]
        except NotFound:
            return None

    def _review_progress(self, conv: dict) -> dict | None:
        """Прогресс быстрого разбора книги разговора: главы пройдено/всего, текущая глава.

        Прогресс разбора живёт отдельно от сессии-урока: сессия — углублённое
        изучение со стейт-машиной, разбор — курсор книги по главам (активность).
        None — разговор без активности; материалы с total_chapters ≤ 1 (видео)
        полосу не показывают, но данные отдаются честными.
        """
        if not conv.get("activity_id"):
            return None
        try:
            act = self._learning.get_activity(conv["activity_id"])
            src = self._library.get_source(act["source_id"])
        except NotFound:
            return None
        total = int(act["total_chapters"])
        done = max(0, min(act["cursor_chapter"] - 1, total))
        finished = total > 0 and done >= total
        current = next((c for c in src.get("chapters", []) if c["idx"] == act["cursor_chapter"]), None)
        return {
            "activity_uid": act["uid"],
            "source_uid": src["uid"],
            "title": act["title"],
            "kind": src["kind"],
            "done_chapters": done,
            "total_chapters": total,
            "current_chapter": None if finished else act["cursor_chapter"],
            "current_title": _chapter_label(current) if not finished and current else None,
            "status": act["status"],
        }

    @staticmethod
    def _scenario(conv: dict, src_kind: str | None = None) -> str:
        """Человекочитаемый сценарий разговора — бейдж «что происходит» вместо режима.

        Старые режимы (quick/session/tuning/agent:*) показываем как есть;
        root/free — по данным: сессия, блок в фокусе, активность с главой.
        """
        mode = conv["mode"]
        if mode.startswith("agent:"):
            return f"Агент {mode.split(':', 1)[1]}"
        if mode == "quick":
            return "Быстрый разбор"
        if mode == "tuning":
            return "Настройка агентов"
        chapter = conv.get("chapter_idx")
        if mode == "session" or conv.get("session"):
            return f"Сессия · глава {chapter}" if chapter else "Сессия-урок"
        if conv.get("focus_block_uid"):
            return "Разбор блока"
        if conv.get("activity_id"):
            if src_kind == "video":
                return "Разбор видео"
            return f"Разбор · глава {chapter}" if chapter else "Разбор материала"
        return "Разговор"

    def _context_block(self, conv: dict, session: dict | None) -> str:
        """Системный блок «Контекст»: профиль, источник, глава, состояние сессии, блок в фокусе."""
        parts = [
            f"Профиль пользователя:\n{self._profile.person_brief()}\n{self._profile.machines_brief()}",
            self._profile.learning_brief(),
        ]
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
                src_lang = (src.get("meta") or {}).get("lang")
                if src_lang and src_lang != "ru":
                    lang_names = {"en": "английский"}
                    parts.append(
                        f"Язык материала: {lang_names.get(src_lang, src_lang)}. Общение, разборы "
                        "и объяснения — всегда на русском; оригинальные цитаты приводи с переводом."
                    )
                chapter_idx = conv.get("chapter_idx") or act["cursor_chapter"]
                chapters = [ch for ch in src.get("chapters", []) if ch["idx"] == chapter_idx]
                if src["kind"] == "video":
                    parts.append(
                        "Режим видео: весь транскрипт — одна запись (chapter=1). Прочитай его ЦЕЛИКОМ: "
                        "read_chapter(chapter=1, limit=6000, offset=…), листай offset по next_offset, "
                        "пока next_offset не станет null. Разбирай видео как единое целое; "
                        "не говори «глава» — только «видео»/«транскрипт»."
                    )
                elif chapters:
                    ch = chapters[0]
                    kp = "; ".join(ch.get("key_points") or [])
                    label = _chapter_label(ch)
                    parts.append(
                        f"Текущая глава {label}: {ch.get('summary') or ''}\n"
                        f"Ключевые пункты: {kp}\n"
                        "Глава считается пройденной, когда пользователь подтвердил разбор "
                        "(«дальше», «понятно», «следующая») — тогда mark_chapter_done."
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
            f"{ch['idx']}. {_chapter_label(ch)} — {(ch.get('summary') or '')[:120]}"
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
            log.info("авто-заголовок не сработал")
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


def _chapter_label(ch: dict) -> str:
    """Читаемое имя главы: номер книги важнее позиционного idx («Глава 3. Ветвление в Git»)."""
    title = ch.get("title") or ""
    inner = re.sub(r"^\s*\d+[.)]?\s+", "", title)
    number = ch.get("number")
    if number:
        return f"Глава {number} ({inner or title})"
    return f"глава {ch.get('idx')}. {title}"
