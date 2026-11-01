"""Сервис обучения: активности, сессии, advance, finish, практика."""

import json
import logging

from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import Conflict, InvalidState, NotFound
from ...kernel.ids import IdGenerator
from .domain import allowed_events, can_finish, transcript_entry, transition
from .events import ActivityProgressed, SessionFinished
from .infra.sql_repo import ActivityRepository, SessionRepository

log = logging.getLogger("learnos.learning")


class LearningService:
    """Use-cases обучения. finish_session без block_json генерирует блок через knowledge."""

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        sessions: SessionRepository,
        activities: ActivityRepository,
        ids: IdGenerator,
        clock: Clock,
        knowledge=None,
        profile=None,
    ) -> None:
        self._uow = uow
        self._sessions = sessions
        self._acts = activities
        self._ids = ids
        self._clock = clock
        self._knowledge = knowledge
        self._profile = profile
        self._chat = None  # ставится в bootstrap (отвязка разговоров при удалении активности)

    def bind_chat(self, chat) -> None:
        """Публичный сервис чата — разговоры отвязываются при удалении активности."""
        self._chat = chat

    # --- активности ---

    def start_activity(self, source_ref: str | int, course_id: int | None = None) -> dict:
        """«Идём по источнику»: курсор на первой главе."""
        from sqlalchemy import select

        from ..library.infra.tables import sources

        now = now_iso(self._clock)
        with self._uow() as uow:
            row = uow.session.execute(select(sources).where(_ref_cond(sources, source_ref))).first()
            if row is None:
                raise NotFound(f"источник '{source_ref}' не найден")
            uid = self._ids.new("act")
            act_id = self._acts.insert(
                uow.session,
                uid=uid,
                source_id=row.id,
                course_id=course_id,
                title=row.title,
                status="active",
                cursor_chapter=1,
                created_at=now,
                updated_at=now,
            )
            return {
                "id": act_id,
                "uid": uid,
                "source_id": row.id,
                "title": row.title,
                "status": "active",
                "cursor_chapter": 1,
            }

    def list_activities(self, status: str | None = None) -> list[dict]:
        """Активности с прогрессом (глав пройдено / всего)."""
        from sqlalchemy import func, select

        from ..library.infra.tables import chapters, sources

        with self._uow() as uow:
            acts = self._acts.list(uow.session, status=status)
            for a in acts:
                total = uow.session.execute(
                    select(func.count()).where(chapters.c.source_id == a["source_id"])
                ).scalar_one()
                a["total_chapters"] = int(total)
                a["source_uid"] = uow.session.execute(
                    select(sources.c.uid).where(sources.c.id == a["source_id"])
                ).scalar_one()
            return acts

    def get_activity(self, ref: str | int) -> dict:
        """Активность с прогрессом."""
        acts = [a for a in self.list_activities() if a["uid"] == str(ref) or a["id"] == _to_int(ref)]
        if not acts:
            raise NotFound(f"активность '{ref}' не найдена")
        return acts[0]

    def activity_ids_for_source(self, source_ref: str | int) -> list[int]:
        """id активностей источника — для фильтра «история разговоров по главе»."""
        with self._uow() as uow:
            from sqlalchemy import select as sa_select

            from ..library.infra.tables import sources as sources_t

            src_id = uow.session.execute(
                sa_select(sources_t.c.id).where(sources_t.c.uid == str(source_ref))
            ).scalar()
            if src_id is None and str(source_ref).isdigit():
                src_id = int(source_ref)
            if src_id is None:
                raise NotFound(f"источник '{source_ref}' не найден")
            return self._acts.ids_for_source(uow.session, int(src_id))

    def release_activities(self, activity_ids: list[int]) -> None:
        """Отвязать сессии от активностей и удалить активности (каскад удаления источника)."""
        if not activity_ids:
            return
        with self._uow() as uow:
            self._sessions.detach_activities(uow.session, activity_ids)
            self._acts.delete_ids(uow.session, activity_ids)

    def delete_activity(self, ref: str | int) -> dict:
        """Удалить активность. Запрещено, если по ней есть сессии (без каскадов, как с источниками).

        Разговоры отвязываются от активности — история чата остаётся.

        Raises:
            NotFound: активности нет.
            Conflict: у активности есть сессии.
        """
        with self._uow() as uow:
            act = self._acts.get(uow.session, ref)
            sessions_count = self._sessions.count_for_activity(uow.session, act["id"])
            if sessions_count:
                raise Conflict(
                    f"у активности «{act['title']}» есть сессии ({sessions_count}) — "
                    "сначала удалите их (блоки базы знаний не должны потерять сессию-источник)"
                )
        if self._chat is not None:
            self._chat.detach_activities([act["id"]])
        with self._uow() as uow:
            self._acts.delete_ids(uow.session, [act["id"]])
        return {"ok": True, "deleted": act["uid"]}

    def delete_session(self, ref: int | str) -> dict:
        """Удалить сессию. Запрещено, если по ней создан блок базы знаний.

        Разговор, из которого шла сессия, остаётся (панель сессии в нём исчезнет).

        Raises:
            NotFound: сессии нет.
            Conflict: по сессии создан блок базы знаний.
        """
        with self._uow() as uow:
            s = self._get(uow.session, ref)
            if self._knowledge is not None and self._knowledge.count_for_session(s["uid"]) > 0:
                raise Conflict("по этой сессии создан блок базы знаний — сначала удалите блок")
            self._sessions.delete(uow.session, s["id"])
        return {"ok": True, "deleted": s["uid"]}

    # --- сессии ---

    def start_session(
        self,
        *,
        course_id: int | None = None,
        activity_ref: str | int | None = None,
        chapter_idx: int | None = None,
        conversation_id: int | None = None,
        config: dict | None = None,
    ) -> dict:
        """Начать сессию: обязательно course_id или activity."""
        if course_id is None and activity_ref is None:
            raise InvalidState("нужен course_id или activity")
        now = now_iso(self._clock)
        with self._uow() as uow:
            activity = None
            if activity_ref is not None:
                activity = self._acts.get(uow.session, activity_ref)
                course_id = course_id or activity["course_id"]
                chapter_idx = chapter_idx or activity["cursor_chapter"]
            idx = (self._sessions.count_for_course(uow.session, course_id) + 1) if course_id else 1
            uid = self._ids.new("ses")
            session_id = self._sessions.insert(
                uow.session,
                uid=uid,
                conversation_id=conversation_id,
                activity_id=activity["id"] if activity else None,
                course_id=course_id,
                chapter_idx=chapter_idx,
                idx=idx,
                status="active",
                state="theory",
                config_json=json.dumps(config or {}, ensure_ascii=False),
                started_at=now,
                transcript_json="[]",
            )
            return self._state_out(self._sessions.get_by_id(uow.session, session_id))

    def get_session_state(self, session_ref: int | str) -> dict:
        """Состояние стейт-машины сессии."""
        with self._uow() as uow:
            s = self._get(uow.session, session_ref)
            return self._state_out(s)

    def advance(self, session_ref: int | str, event: str, payload: dict | None = None) -> dict:
        """Продвинуть сессию: переход или лог-событие. Возвращает карточку для UI-событий.

        Raises:
            InvalidState: сессия не активна или событие недопустимо.
        """
        now = now_iso(self._clock)
        card = None
        with self._uow() as uow:
            s = self._get(uow.session, session_ref)
            if s["status"] != "active":
                raise InvalidState(f"сессия {s['status']}, advance denied")
            try:
                new_state = transition(s["state"], event)
            except ValueError as e:
                raise InvalidState(str(e), code="invalid_event") from e
            payload = payload or {}
            transcript = s["transcript"] + [transcript_entry(s["state"], event, payload, now)]
            self._sessions.update(
                uow.session,
                s["id"],
                state=new_state,
                transcript_json=json.dumps(transcript, ensure_ascii=False),
            )
            card = self._card_for_event(event, payload, transcript)
            result = self._state_out({**s, "state": new_state, "transcript": transcript})
            result["_card"] = card
            return result

    def practice_step(
        self,
        session_ref: int | str,
        machine: str,
        command: str,
        explanation: str,
        expected: str | None = None,
        risk: str = "low",
    ) -> dict:
        """Шаг практики: лог + карточка команды. Машина проверяется по профилю."""
        if risk not in {"low", "medium", "high"}:
            raise InvalidState("risk должен быть low|medium|high")
        if self._profile is not None:
            self._profile.ensure_machine(machine)
        result = self.advance(
            session_ref,
            "practice_log",
            {
                "machine": machine,
                "command": command,
                "explanation": explanation,
                "expected": expected,
                "risk": risk,
            },
        )
        machine_name = machine
        if self._profile is not None:
            machine_name = next((m.name for m in self._profile.get().machines if m.id == machine), machine)
        result["_card"] = {
            "type": "command",
            "machine": machine,
            "machine_name": machine_name,
            "command": command,
            "explanation": _split_explanation(explanation),
            "expected": expected,
            "risk": risk,
        }
        return result

    def finish_session(self, session_ref: int | str, block_draft: dict | None = None) -> dict:
        """Завершить сессию (только из debrief) и сохранить блок в KB.

        Порядок: сначала блок (генерация может упасть — сессия останется в debrief,
        и finish можно повторить), потом закрытие. Если блок по сессии уже сохранён
        (прошлый финиш упал после записи) — повтор идемпотентен: блока-дубля не будет.
        Без block_draft блок генерируется из транскрипта (block_writer через knowledge).
        """
        now = now_iso(self._clock)
        with self._uow() as uow:
            s = self._get(uow.session, session_ref)
            try:
                can_finish(s["state"], s["status"])
            except ValueError as e:
                raise InvalidState(str(e)) from e

        # 1) блок знаний — до закрытия: сбой LLM не должен стоить урока (R-03)
        block = self._knowledge.block_card_for_session(s["uid"]) or self._write_block(s, block_draft)
        (self._maybe_write_runbook(s, block["block_uid"]) or {}).get("block_uid")

        # 2) закрытие сессии + курсор активности + события
        with self._uow() as uow:
            self._sessions.update(uow.session, s["id"], status="finished", state="done", ended_at=now)
            activity = self._acts.find(uow.session, s["activity_id"]) if s["activity_id"] else None
            if activity:
                from sqlalchemy import func, select

                from ..library.infra.tables import chapters

                total = int(
                    uow.session.execute(
                        select(func.count()).where(chapters.c.source_id == activity["source_id"])
                    ).scalar_one()
                )
                cursor = max(activity["cursor_chapter"], (s["chapter_idx"] or 0) + 1)
                status = "done" if cursor > total else activity["status"]
                self._acts.update(
                    uow.session, activity["id"], cursor_chapter=cursor, status=status, updated_at=now
                )
                uow.emit(
                    ActivityProgressed(
                        activity_uid=activity["uid"], cursor_chapter=cursor, total_chapters=total
                    )
                )
            uow.emit(SessionFinished(session_uid=s["uid"], block_uid=block["block_uid"]))
        return {
            "ok": True,
            "block_uid": block["block_uid"],
            "session_uid": s["uid"],
            "path": block.get("path"),
            "_card": block.get("_card"),
        }

    def mark_chapter_done(
        self,
        *,
        activity_ref: str | int | None = None,
        chapter: int | None = None,
        conversation_uid: str | None = None,
    ) -> dict:
        """Отметить главу разобранной: курсор активности двигается вперёд (не назад).

        Доступен quick-разбору: без сессии-урока прогресс по книге всё равно должен
        двигаться. Активность — по явной ссылке или из разговора (conversation_uid).
        """
        now = now_iso(self._clock)
        with self._uow() as uow:
            if activity_ref is not None:
                act = self._acts.get(uow.session, activity_ref)
            elif conversation_uid is not None and self._chat is not None:
                activity_id = self._chat.activity_id_for_conversation(conversation_uid)
                if activity_id is None:
                    raise NotFound(f"разговор '{conversation_uid}' не привязан к активности")
                act = self._acts.get(uow.session, activity_id)
            else:
                raise NotFound("активность не задана (activity или conversation)")
            from sqlalchemy import func, select

            from ..library.infra.tables import chapters as chapters_t

            total = int(
                uow.session.execute(
                    select(func.count()).where(chapters_t.c.source_id == act["source_id"])
                ).scalar_one()
            )
            target = chapter if chapter is not None and chapter > 0 else act["cursor_chapter"]
            cursor = max(act["cursor_chapter"], target + 1)
            status = "done" if cursor > total > 0 else act["status"]
            self._acts.update(uow.session, act["id"], cursor_chapter=cursor, status=status, updated_at=now)
            uow.emit(ActivityProgressed(activity_uid=act["uid"], cursor_chapter=cursor, total_chapters=total))
        return {
            "ok": True,
            "activity": act["uid"],
            "marked_chapter": target,
            "cursor_chapter": cursor,
            "total_chapters": total,
            "status": status,
        }

    def session_for_conversation(self, conversation_id: int) -> dict | None:
        """Активная сессия разговора (для агента session-режима)."""
        with self._uow() as uow:
            s = self._sessions.find_by_conversation(uow.session, conversation_id)
            return self._state_out(s) if s else None

    # --- внутреннее ---

    def _get(self, session, ref):
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return self._sessions.get_by_id(session, int(ref))
        return self._sessions.get_by_uid(session, str(ref))

    def _write_block(self, s: dict, draft: dict | None) -> dict:
        """Блок из явного драфта или генерация из транскрипта."""
        from ..knowledge.schemas import BlockDraftIn

        if draft:
            draft_in = BlockDraftIn.model_validate(draft)
            domain_draft = draft_in.to_domain()
            if not domain_draft.category_suggestion:
                domain_draft = self._knowledge.categorize_draft(domain_draft)
            block = self._knowledge.save_block(
                domain_draft,
                session_uid=s["uid"],
                activity_uid=None,
                category_status="confirmed",
            )
        else:
            generated = self._knowledge.generate_from_transcript(s)
            block = self._knowledge.save_block(generated, session_uid=s["uid"], category_status="confirmed")
        return {
            "block_uid": block.meta.uid,
            "path": block.meta.path,
            "_card": {
                "type": "block_saved",
                "block_uid": block.meta.uid,
                "kind": block.meta.kind,
                "title": block.meta.title,
                "summary": block.meta.summary,
                "category": block.meta.category_path,
                "category_status": "confirmed",
                "version": 1,
            },
        }

    def _maybe_write_runbook(self, s: dict, lesson_uid: str) -> dict | None:
        """Runbook после урока, если в сессии ≥ 2 шагов практики (этап 8 E)."""
        steps = [e for e in (s.get("transcript") or []) if e.get("event") == "practice_log"]
        if len(steps) < 2 or self._knowledge is None:
            return None
        try:
            draft = self._knowledge.generate_runbook(s, lesson_uid)
        except Exception:  # noqa: BLE001 — runbook не должен ронять finish_session
            log.warning("runbook_writer не сработал", exc_info=True)
            return None
        block = self._knowledge.save_block(draft, session_uid=s["uid"], category_status="suggested")
        return {"block_uid": block.meta.uid}

    def _state_out(self, s: dict) -> dict:
        return {
            "session_id": s["id"],
            "session_uid": s["uid"],
            "course_id": s["course_id"],
            "activity_id": s["activity_id"],
            "chapter_idx": s["chapter_idx"],
            "idx": s["idx"],
            "status": s["status"],
            "state": s["state"],
            "config": s["config"],
            "started_at": s["started_at"],
            "ended_at": s["ended_at"],
            "transcript": s["transcript"],
            "allowed_events": list(allowed_events(s["state"])),
        }

    @staticmethod
    def _card_for_event(event: str, payload: dict, transcript: list[dict]) -> dict | None:
        """Карточки UI для лог-событий: вопрос/оценка/примечание."""
        if event == "ask":
            questions = [t for t in transcript if t["event"] == "ask"]
            return {
                "type": "question",
                "concept": payload.get("concept", ""),
                "question": payload.get("question", ""),
                "index": len(questions),
                "total": payload.get("total"),
            }
        if event == "answer":
            return {
                "type": "evaluation",
                "verdict": payload.get("verdict", ""),
                "comment": payload.get("comment", ""),
                "weak_spot": payload.get("weak_spot"),
            }
        if event == "note" and payload.get("weak_spot"):
            return {
                "type": "evaluation",
                "verdict": "partial",
                "comment": payload.get("comment", ""),
                "weak_spot": payload.get("weak_spot"),
            }
        return None


def _split_explanation(explanation: str) -> list[dict]:
    """Разбор объяснения команды на части (если агент передал 'part — text; …')."""
    parts = []
    for piece in explanation.split(";"):
        if "—" in piece:
            k, v = piece.split("—", 1)
            parts.append({"part": k.strip(), "text": v.strip()})
        elif piece.strip():
            parts.append({"part": "", "text": piece.strip()})
    return parts or [{"part": "", "text": explanation}]


def _ref_cond(table, ref):
    if isinstance(ref, str) and not ref.isdigit():
        return table.c.uid == ref
    return table.c.id == int(ref)


def _to_int(ref) -> int | None:
    try:
        return int(ref)
    except (TypeError, ValueError):
        return -1
