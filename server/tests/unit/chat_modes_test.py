"""Режимы чата: MODES (схемы) и AGENT_BY_MODE (сервис) согласованы."""

from app.modules.chat.schemas import MODES
from app.modules.chat.service import AGENT_BY_MODE, RESEARCH_DIRECTIVE


def test_agent_by_mode_covers_all_modes():
    assert set(AGENT_BY_MODE) == set(MODES), "новый режим чата должен получить агента"


def test_research_directive_adds_sources_only_by_consent():
    """Ресёрч не добавляет источники сам: карточка offer_action → согласие → добавление (BUG-006)."""
    assert "offer_action" in RESEARCH_DIRECTIVE
    assert "НИЧЕГО не добавляй" in RESEARCH_DIRECTIVE
    # пользователь может править список прямо в ответе («добавь только первые два»)
    assert "добавь именно выбранные" in RESEARCH_DIRECTIVE
    # старое поведение — «добавь сам в Библиотеку» — запрещено возвращать
    assert "добавь сам" not in RESEARCH_DIRECTIVE


def _svc_with_source(lang: str | None):
    """ChatService только с зависимостями контекст-билдера (без проводки контейнера)."""
    from types import SimpleNamespace

    from app.modules.chat.service import ChatService

    svc = ChatService.__new__(ChatService)
    svc._profile = SimpleNamespace(
        person_brief=lambda: "имя", machines_brief=lambda: "машины", learning_brief=lambda: "стиль"
    )
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
