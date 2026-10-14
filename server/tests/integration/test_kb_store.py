"""MdBlockStore: запись/чтение MD-блоков и дерева категорий на tmp-каталоге."""

import pytest

from app.kernel.errors import NotFound
from app.modules.knowledge.domain import BlockDraft, Concept, default_categories
from app.modules.knowledge.infra.md_store import MdBlockStore


def make_draft(title: str = "Тестовый блок") -> BlockDraft:
    return BlockDraft(
        title=title,
        summary="сводка",
        concepts=(Concept("термин", "определение"),),
        theses=("тезис один",),
        tags=("tag1",),
    )


def test_write_read_and_read_meta_roundtrip(tmp_path):
    store = MdBlockStore(tmp_path)
    stem = store.write(
        "blk_aaaa1111",
        make_draft(),
        {"created": "2026-01-01T10:00:00", "updated": "2026-01-02", "version": 1},
    )

    # имя файла = <uid>_<slug>.md
    assert stem.startswith("blk_aaaa1111")
    assert store.list_stems() == [stem]

    content = store.read(stem)
    assert content.startswith("---")

    meta = store.read_meta(stem)
    assert meta.uid == "blk_aaaa1111"
    assert meta.title == "Тестовый блок"
    assert meta.kind == "lesson"
    assert meta.summary == "сводка"
    assert meta.tags == ("tag1",)
    assert meta.version == 1
    # YAML парсит дату в datetime; read_meta приводит к строке — проверяем префикс
    assert meta.created.startswith("2026-01-01")
    assert meta.updated.startswith("2026-01-02")
    assert meta.category_status == "suggested"


def test_write_with_existing_name_reuses_file(tmp_path):
    """Правка блока не плодит файлы: existing_name переиспользуется."""
    store = MdBlockStore(tmp_path)
    stem1 = store.write(
        "blk_aaaa1111", make_draft(), {"created": "2026-01-01", "updated": "2026-01-01", "version": 1}
    )
    stem2 = store.write(
        "blk_aaaa1111",
        make_draft(title="Новое название"),
        {"created": "2026-01-01", "updated": "2026-01-02", "version": 2},
        existing_name=stem1,
    )

    assert stem1 == stem2
    assert store.list_stems() == [stem1]
    assert store.read_meta(stem1).version == 2
    assert "Новое название" in store.read(stem1)


def test_read_missing_file_raises_not_found(tmp_path):
    store = MdBlockStore(tmp_path)
    with pytest.raises(NotFound):
        store.read("blk_nothx00")


def test_write_raw_overwrites_whole_file(tmp_path):
    store = MdBlockStore(tmp_path)
    stem = store.write(
        "blk_aaaa1111", make_draft(), {"created": "2026-01-01", "updated": "2026-01-01", "version": 1}
    )
    store.write_raw(stem, "---\nid: blk_aaaa1111\ntitle: Новое\n---\n\n# тело")
    assert "title: Новое" in store.read(stem)


def test_categories_yaml_roundtrip(tmp_path):
    store = MdBlockStore(tmp_path)
    store.write_categories(default_categories())

    restored = store.read_categories()

    assert {c.path for c in restored} == {c.path for c in default_categories()}
    assert {c.title for c in restored} == {c.title for c in default_categories()}


def test_categories_empty_without_file(tmp_path):
    assert MdBlockStore(tmp_path).read_categories() == []
