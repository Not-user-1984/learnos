"""Эвристика куратора структуры (фолбэк без LLM): классы записей TOC и номера глав."""

from app.modules.library.domain import (
    classify_toc_entry,
    merge_curator_labels,
    parse_chapter_number,
)


def test_parse_chapter_number_variants():
    assert parse_chapter_number("Глава 3. Ветвление в Git") == 3
    assert parse_chapter_number("ГЛАВА 12 — Инструменты") == 12
    assert parse_chapter_number("Chapter 5. Distributed Git") == 5
    assert parse_chapter_number("10. Git изнутри") == 10
    assert parse_chapter_number("2) Основы") == 2
    assert parse_chapter_number("Введение") is None
    assert parse_chapter_number("Приложение A. Команды") is None
    assert parse_chapter_number("") is None


def test_classify_front_matter_by_stop_words():
    titles = ("Оглавление", "Contents", "Subject Index", "Предметный указатель", "Лицензия", "Посвящение")
    for title in titles:
        assert classify_toc_entry(title, page_count=30) == "front_matter", title


def test_classify_front_matter_by_short_length():
    # 1–2 страницы содержательного названия — обычно титул/выходные данные
    assert classify_toc_entry("Введение", page_count=1) == "front_matter"


def test_classify_chapter_and_appendix():
    assert classify_toc_entry("Введение", page_count=12) == "chapter"
    assert classify_toc_entry("Глава 2. Основы Git", page_count=20) == "chapter"
    assert classify_toc_entry("Приложение A. Шпаргалка Git", page_count=2) == "appendix"
    assert classify_toc_entry("Appendix B. Embedding Git", page_count=5) == "appendix"
    # «Введение» — настоящая глава, не мусор
    assert classify_toc_entry("Introduction", page_count=15) == "chapter"


# ── жёсткие правила эвристики поверх LLM-куратора ──────────────────────────────


def _entry(idx: int, title: str, pages: int) -> dict:
    return {"idx": idx, "title": title, "page_count": pages}


def test_merge_hard_rules_beat_llm_for_short_prefaces():
    """LLM тащит короткие предисловия в главы — жёсткое правило вырезает их."""
    entries = [
        _entry(1, "Предисловие", 2),
        _entry(2, "Пролог от Бена Страуба", 1),
        _entry(3, "Введение", 15),
        _entry(4, "Глава 2. Основы Git", 30),
    ]
    heuristic = {e["idx"]: classify_toc_entry(e["title"], e["page_count"]) for e in entries}
    llm = {1: "chapter", 2: "chapter", 3: "chapter", 4: "chapter"}
    merged = merge_curator_labels(entries, heuristic, llm)
    assert merged == {1: "front_matter", 2: "front_matter", 3: "chapter", 4: "chapter"}


def test_merge_keeps_short_introduction_as_llm_chapter():
    """Короткое «Введение» — не preface-слово: LLM может оставить его главой."""
    entries = [_entry(1, "Введение", 2), _entry(2, "Глава 1. Начало", 25)]
    heuristic = {1: "front_matter", 2: "chapter"}  # эвристика по длине выкинула бы
    llm = {1: "chapter", 2: "chapter"}
    assert merge_curator_labels(entries, heuristic, llm) == {1: "chapter", 2: "chapter"}


def test_merge_stop_words_always_win():
    entries = [_entry(1, "Оглавление", 3), _entry(2, "Лицензия", 4)]
    llm = {1: "chapter", 2: "appendix"}
    assert merge_curator_labels(entries, {"1": "front_matter", "2": "front_matter"}, llm) == {
        1: "front_matter",
        2: "front_matter",
    }


def test_merge_without_llm_uses_heuristic():
    entries = [_entry(1, "Титул", 1), _entry(2, "Введение", 10)]
    heuristic = {1: "front_matter", 2: "chapter"}
    assert merge_curator_labels(entries, heuristic, None) == heuristic
