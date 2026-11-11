"""Сервис «Сегодня»: снимок «что делать дальше» для главной страницы (B-005).

Только публичные сервисы других модулей (никакой чужой инфры — контракт линтера);
каждый пункт несёт action — куда вести пользователя одной кнопкой.
"""


class TodayService:
    """Use-case одного запроса: собрать дашборд дня."""

    def __init__(self, learning, courses, library, knowledge, review, chat) -> None:
        self._learning = learning
        self._courses = courses
        self._library = library
        self._knowledge = knowledge
        self._review = review
        self._chat = chat

    def snapshot(self) -> dict:
        """Снимок дня: активная сессия, следующие элементы курсов, чтение,
        повторения, входящие KB, источники в обработке/с ошибкой."""
        return {
            "active_session": self._active_session(),
            "next_course_items": self._next_course_items(limit=3),
            "reading": self._reading(limit=3),
            "review": {"due_today": self._review.stats()["due_today"]},
            "inbox_count": len(self._knowledge.inbox()),
            "sources_attention": self._sources_attention(limit=5),
        }

    def _active_session(self) -> dict | None:
        """Незакрытая сессия-урок: вернуться в её разговор."""
        sessions = self._learning.active_sessions()
        if not sessions:
            return None
        s = sessions[0]
        conversation_uid = (
            self._chat.conversation_uid(s["conversation_id"]) if s.get("conversation_id") else None
        )
        return {
            "session_uid": s["session_uid"],
            "conversation_uid": conversation_uid,
            "chapter_idx": s.get("chapter_idx"),
            "started_at": s.get("started_at"),
        }

    def _next_course_items(self, limit: int) -> list[dict]:
        """Первые незакрытые элементы курсов (курс = доска, B-004); завершённые
        курсы не предлагаются, planned — предлагаются («что начать»)."""
        out: list[dict] = []
        for course in self._courses.list_courses():
            if course["status"] == "done":
                continue
            full = self._courses.get_course(course["uid"])
            item = full.get("next_step")
            if not item:
                continue
            out.append(
                {
                    "course_uid": course["uid"],
                    "course_title": course["title"],
                    "item_id": item["item_id"],
                    "item_type": item["item_type"],
                    "title": item["title"],
                    "hint": item["hint"],
                }
            )
            if len(out) >= limit:
                break
        return out

    def _reading(self, limit: int) -> list[dict]:
        """Незаконченные книги/видео: продолжить с текущей главы."""
        out = []
        for act in self._learning.list_activities(status="active"):
            out.append(
                {
                    "activity_uid": act["uid"],
                    "source_uid": act.get("source_uid"),
                    "title": act["title"],
                    "cursor_chapter": act["cursor_chapter"],
                    "total_chapters": act.get("total_chapters", 0),
                }
            )
            if len(out) >= limit:
                break
        return out

    def _sources_attention(self, limit: int) -> list[dict]:
        """Источники в обработке или с ошибкой — требуют внимания."""
        out = []
        for src in self._library.list_sources():
            if src["status"] not in {"processing", "failed"}:
                continue
            out.append(
                {
                    "source_uid": src["uid"],
                    "title": src["title"],
                    "status": src["status"],
                    "last_error": src.get("last_error"),
                }
            )
            if len(out) >= limit:
                break
        return out
