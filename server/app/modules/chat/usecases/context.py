"""Контекст разговора для агента: источник, сессия, прогресс, сценарий (B-009)."""

from ....kernel.errors import NotFound
from .scenarios import chapter_label as _chapter_label


class ContextBuilder:
    """Перенос из chat/service.py без изменения поведения."""

    def __init__(self, svc) -> None:
        self._svc = svc

    def _activity_source_kind(self, conv: dict) -> str | None:
        """Тип источника активности разговора (для сценария «Разбор видео/материала»)."""
        if not conv.get("activity_id"):
            return None
        try:
            act = self._svc._learning.get_activity(conv["activity_id"])
            return self._svc._library.get_source(act["source_id"])["kind"]
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
            act = self._svc._learning.get_activity(conv["activity_id"])
            src = self._svc._library.get_source(act["source_id"])
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
            "Профиль пользователя:\n"
            f"{self._svc._profile.person_brief()}\n{self._svc._profile.machines_brief()}",  # noqa: SLF001
            self._svc._profile.learning_brief(),
        ]
        if conv.get("activity_id"):
            try:
                act = self._svc._learning.get_activity(conv["activity_id"])
                src = self._svc._library.get_source(act["source_id"])
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
                b = self._svc._knowledge.get_block(conv["focus_block_uid"])
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
        profile = self._svc._profile.get()
        config = {
            "concepts": profile.learning.theory_concepts,
            "questions_per_block": profile.learning.questions_per_concept,
            "practice": profile.learning.practice_default,
            "minutes": profile.learning.session_minutes,
        }
        activity = self._svc._learning.get_activity(conv["activity_id"]) if conv.get("activity_id") else None
        return self._svc._learning.start_session(
            activity_ref=activity["id"] if activity else None,
            chapter_idx=conv.get("chapter_idx"),
            conversation_id=conv["id"],
            config=config,
        )
