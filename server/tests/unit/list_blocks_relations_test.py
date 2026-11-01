"""R-09: list_blocks отдаёт tags/sources — карточки БЗ с источником, главы курса засчитываются."""

from app.modules.knowledge.domain import BlockDraft, BlockSource


def test_list_blocks_returns_tags_and_sources(container):
    """Фильтр/список отдаёт связи блока, а не пустые кортежи (R-09)."""
    k = container.knowledge
    block = k.save_block(
        BlockDraft(
            title="Урок с источником",
            theses=("тезис",),
            tags=("k8s", "net"),
            category_suggestion="infra/kubernetes",
            sources=(BlockSource(source="src_test0001", chapter=3, title="Book"),),
        ),
        category_status="confirmed",
    )

    listed = k.list_blocks()
    mine = next(m for m in listed if m.uid == block.meta.uid)
    assert set(mine.tags) == {"k8s", "net"}
    assert mine.sources and mine.sources[0].source == "src_test0001"
    assert mine.sources[0].chapter == 3


def test_course_chapter_marks_done_via_block_source(container, client):
    """Элемент курса «глава» засчитывается, когда по главе есть блок (R-09)."""
    # источник с двумя главами
    src = client.post(
        "/api/sources",
        json={"kind": "video", "title": "Видео-курс", "url": "https://youtu.be/test99999"},
    ).json()
    # блок по главе 1 этого источника
    container.knowledge.save_block(
        BlockDraft(
            title="Конспект видео",
            theses=("тезис",),
            category_suggestion="life",
            sources=(BlockSource(source=src["uid"], chapter=1, title="Видео-курс"),),
        ),
        category_status="confirmed",
    )

    course = client.post("/api/courses", json={"topic": "видео-курс"}).json()
    client.post(
        f"/api/courses/{course['id']}/items",
        json={"item_type": "chapter", "source": src["id"], "chapter": 1},
    )
    detail = client.get(f"/api/courses/{course['id']}").json()
    assert detail["items_done"] == 1
    assert detail["items"][0]["done"] is True
    assert detail["next_step"] is None
