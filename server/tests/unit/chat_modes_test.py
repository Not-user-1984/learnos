"""Режимы чата: MODES (схемы) и AGENT_BY_MODE (сервис) согласованы."""

from app.modules.chat.schemas import MODES
from app.modules.chat.service import AGENT_BY_MODE


def test_agent_by_mode_covers_all_modes():
    assert set(AGENT_BY_MODE) == set(MODES), "новый режим чата должен получить агента"


def _svc_with_source(lang: str | None):
    """ChatService только с зависимостями контекст-билдера (без проводки контейнера)."""
    from types import SimpleNamespace

    from app.modules.chat.service import ChatService

    svc = ChatService.__new__(ChatService)
    svc._profile = SimpleNamespace(machines_brief=lambda: "машины", learning_brief=lambda: "стиль")
    svc._learning = SimpleNamespace(
        get_activity=lambda _a: {
            "id": 1,
            "title": "Книга",
            "cursor_chapter": 1,
            "total_chapters": 3,
            "source_id": 7,
        }
    )
    meta = {"lang": lang} if lang else {}
    svc._library = SimpleNamespace(
        get_source=lambda _s: {
            "uid": "src_x",
            "kind": "book",
            "title": "Some Book",
            "meta": meta,
            "summary": "",
            "chapters": [{"idx": 1, "title": "Chapter 1", "summary": "", "key_points": []}],
        }
    )
    svc._knowledge = SimpleNamespace()
    return svc


def test_context_directive_for_foreign_source():
    """Не-ru источник → в системном контексте директива русского диалога (T-032)."""
    conv = {"activity_id": 1, "chapter_idx": 1, "mode": "quick", "focus_block_uid": None}
    block = _svc_with_source("en")._context_block(conv, None)
    assert "Язык материала: английский" in block
    assert "всегда на русском" in block


def test_context_no_directive_for_russian_source():
    """ru-источник и источник без lang — директивы нет (NULL трактуем как ru/неопределено)."""
    conv = {"activity_id": 1, "chapter_idx": 1, "mode": "quick", "focus_block_uid": None}
    assert "Язык материала" not in _svc_with_source("ru")._context_block(conv, None)
    assert "Язык материала" not in _svc_with_source(None)._context_block(conv, None)
