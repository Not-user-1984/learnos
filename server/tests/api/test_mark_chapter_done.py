"""mark_chapter_done: quick-разбор двигает курсор активности через разговор."""

from tests.api.test_book_structure import ENTRIES, _add_book_source


def test_mark_chapter_done_moves_cursor_via_conversation(client, container):
    """Тул по conversation_uid: вперёд, но не назад; последняя глава завершает активность."""
    src = _add_book_source(container)
    container.library._curate_book(src["id"], src["uid"], {"entries": ENTRIES})
    act = container.learning.start_activity(src["uid"])
    conv = container.chat.create_conversation(mode="quick", activity=act["uid"], chapter=1)

    spec = container.tools.get("mark_chapter_done")
    assert "agent" in spec.channels  # modes-поле удалено как мёртвое (R-28)

    out = container.learning.mark_chapter_done(conversation_uid=conv["uid"])
    assert out["cursor_chapter"] == 2 and out["marked_chapter"] == 1

    # явный номер главы: вперёд до 3; назад не откатывает
    out = container.learning.mark_chapter_done(conversation_uid=conv["uid"], chapter=2)
    assert out["cursor_chapter"] == 3
    out = container.learning.mark_chapter_done(conversation_uid=conv["uid"], chapter=1)
    assert out["cursor_chapter"] == 3

    # последняя глава → активность завершена
    out = container.learning.mark_chapter_done(conversation_uid=conv["uid"], chapter=3)
    assert out["status"] == "done"
