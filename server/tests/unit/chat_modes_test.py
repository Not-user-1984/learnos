"""Режимы чата: MODES/AGENT_BY_MODE согласованы; кнопки-ответы (T-045), блочный разбор (T-046 Э2)."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.kernel.tools.spec import ToolContext
from app.modules.chat.agents import free_chat, quick_reviewer, root, session_tutor
from app.modules.chat.schemas import MODES
from app.modules.chat.service import AGENT_BY_MODE, INTENT_DIRECTIVES, RESEARCH_DIRECTIVE
from app.modules.chat.tools import OfferRepliesArgs, ShowChapterReviewArgs, chat_tools


def test_agent_by_mode_covers_all_modes():
    assert set(AGENT_BY_MODE) == set(MODES), "новый режим чата должен получить агента"


def test_offer_replies_returns_quick_replies_card():
    """offer_replies прикладывает карточку quick_replies — варианты ответа без парсинга текста."""
    tools = {t.name: t for t in chat_tools(SimpleNamespace())}
    out = tools["offer_replies"].handler(
        OfferRepliesArgs(replies=["Дальше", "Подробнее", "Сессия по этой главе"]), ToolContext()
    )
    assert out["_card"]["type"] == "quick_replies"
    assert out["_card"]["replies"] == ["Дальше", "Подробнее", "Сессия по этой главе"]


def test_offer_replies_lives_in_tutor_toolsets():
    """Кнопки-ответы доступны тьюторам, которые спрашивают короткий выбор (root наследует free_chat)."""
    for spec in (free_chat, quick_reviewer, session_tutor):
        assert "offer_replies" in spec.tools, f"{spec.name} должен уметь предлагать кнопки-ответы"


def _review_args(**overrides) -> ShowChapterReviewArgs:
    """Валидные аргументы разбора главы; переопределения — для проверки лимитов."""
    base = dict(
        title="Глава 3. Процессы",
        key_points=[
            "Процесс = программа в выполнении",
            "Контекст — снимок состояния",
            "fork порождает копию",
        ],
        concepts=[{"term": "процесс", "definition": "программа в выполнении"}],
        applicable=["ps aux на твоём маке покажет процессы терминала"],
        questions=["Чем процесс отличается от потока?"],
    )
    base.update(overrides)
    return ShowChapterReviewArgs(**base)


def test_show_chapter_review_returns_card():
    """show_chapter_review оформляет итог разбора карточкой chapter_review со всеми секциями."""
    tools = {t.name: t for t in chat_tools(SimpleNamespace())}
    args = _review_args(
        media="video",
        key_points=["Пункты", "не обязаны", "быть длинными", "тут четыре"],
    )
    out = tools["show_chapter_review"].handler(args, ToolContext())
    assert out["_card"]["type"] == "chapter_review"
    assert out["_card"]["media"] == "video"
    assert out["_card"]["title"] == "Глава 3. Процессы"
    assert len(out["_card"]["key_points"]) == 4
    assert out["_card"]["concepts"] == [{"term": "процесс", "definition": "программа в выполнении"}]
    assert out["_card"]["applicable"] and out["_card"]["questions"]


def test_show_chapter_review_validates_sections():
    """Секции карточки жёстко ограничены: 3–5 пунктов главного, 1–2 вопроса, media — chapter|video."""
    with pytest.raises(ValidationError):
        _review_args(key_points=["один", "два"])
    with pytest.raises(ValidationError):
        _review_args(questions=["много", "вопросов", "сразу"])
    with pytest.raises(ValidationError):
        _review_args(media="podcast")


def test_show_chapter_review_lives_in_review_toolsets():
    """Карточку разбора показывают quick_reviewer и root (root ведёт интент «review» единого входа)."""
    for spec in (quick_reviewer, root):
        assert "show_chapter_review" in spec.tools, f"{spec.name} должен показывать разбор карточкой"
    assert "show_chapter_review" not in free_chat.tools
    # директива интента «review» ведёт к карточке, а не к текстовой простыне
    assert "show_chapter_review" in INTENT_DIRECTIVES["review"]


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
