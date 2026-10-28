"""Претрекер контента: чистая функция, без БД и LLM (T-036)."""

from app.modules.chat.domain import content_note, detect_content


def kinds(text: str) -> list[str]:
    return [s.kind for s in detect_content(text)]


def test_youtube_link_recognized():
    """YouTube-ссылка (watch и youtu.be) → сигнал youtube с подсказкой add_source(kind=video)."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    signals = detect_content(f"посмотри {url} очень полезно")
    assert kinds(f"{url}") == ["youtube"]
    assert signals[0].value == url
    assert "add_source(kind=video" in signals[0].hint
    assert kinds("https://youtu.be/dQw4w9WgXcQ") == ["youtube"]
    assert kinds("https://m.youtube.com/shorts/abcdefghijk") == ["youtube"]


def test_youtube_not_duplicated_as_generic_url():
    """Ссылка YouTube не появляется второй раз как произвольный URL."""
    signals = detect_content("https://youtube.com/watch?v=dQw4w9WgXcQ и https://example.com/post")
    assert [s.kind for s in signals] == ["youtube", "url"]


def test_plain_url_recognized():
    """Произвольная ссылка → сигнал url; хвостовая пунктуация срезается."""
    signals = detect_content("статья: https://example.com/deep/path?a=1.")
    assert [s.kind for s in signals] == ["url"]
    assert signals[0].value == "https://example.com/deep/path?a=1"
    assert "web_read" in signals[0].hint
    assert "add_source(kind=web" in signals[0].hint


def test_arxiv_id_recognized():
    """arXiv с префиксом или ссылкой на abs; голый id без префикса не матчится (ложные срабатывания)."""
    signals = detect_content("см. arXiv:2401.12345v2")
    assert [s.kind for s in signals] == ["arxiv"]
    assert signals[0].value == "arXiv:2401.12345"
    assert "academic_search" in signals[0].hint
    assert kinds("разобрали arxiv.org/abs/2401.12345") == ["arxiv"]
    assert kinds("версия 2401.12345 без префикса") == []


def test_doi_recognized():
    """DOI → сигнал doi с подсказкой academic_search."""
    signals = detect_content("работа doi:10.1000/xyz.123")
    assert [s.kind for s in signals] == ["doi"]
    assert signals[0].value == "10.1000/xyz.123"
    assert "academic_search" in signals[0].hint


def test_clean_text_no_signals():
    """Обычный текст без ссылок — заметки нет."""
    assert detect_content("как устроен pod в кубернетесе?") == []
    assert content_note("просто вопрос про git rebase") == ""


def test_note_lists_all_signals():
    """Заметка перечисляет все распознанные ссылки; повтор одной ссылки — одна строка."""
    note = content_note(
        "видео https://youtu.be/dQw4w9WgXcQ и снова https://youtu.be/dQw4w9WgXcQ, "
        "статья https://example.com/a"
    )
    assert note.startswith("Распознан контент")
    assert note.count("YouTube-ссылка") == 1  # дедуп
    assert "example.com" in note
