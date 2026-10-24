"""Эвристика куратора структуры (фолбэк без LLM): классы записей TOC и номера глав."""

from app.modules.library.domain import classify_toc_entry, parse_chapter_number


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
