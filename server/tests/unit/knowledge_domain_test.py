"""Домен базы знаний: slugify, сборка/разбор MD, патчи драфта, категории."""

import pytest

from app.modules.knowledge.domain import (
    Concept,
    PracticeStep,
    apply_patch,
    category_ancestors,
    draft_to_markdown,
    extract_links,
    normalize_category_path,
    parse_markdown,
    slugify,
)


def make_draft():
    """Драфт со всеми секциями — для roundtrip-тестов."""
    from app.modules.knowledge.domain import BlockDraft, BlockSource

    return BlockDraft(
        title="Сетевая модель подов",
        summary="CNI и pause-контейнер",
        kind="lesson",
        concepts=(Concept("Pod", "минимальный юнит развертывания"),),
        theses=("У каждого пода свой network namespace",),
        my_examples=("Как вагоны у локомотива",),
        mermaid="graph TD\n  A[Pod] --> B[pause]",
        practice=(PracticeStep(machine="mac", command="kubectl get pods", explanation="посмотреть поды"),),
        weak_spots=("не понимаю veth-пары",),
        open_questions=("кто выдаёт IP?",),
        links=("blk_deadbeef",),
        tags=("k8s", "net"),
        category_suggestion="infra/kubernetes",
        sources=(BlockSource(source="src_12345678", chapter=1, title="K8s Book"),),
    )


# --- slugify ---


def test_slugify_transliterates_cyrillic():
    assert slugify("Привет Мир") == "privet-mir"


def test_slugify_empty_and_punctuation():
    assert slugify("") == ""
    assert slugify("Kubernetes: Network! --- Basics") == "kubernetes-network-basics"


def test_slugify_limits_length():
    assert len(slugify("очень длинное название книги про кубернетес и сети")) <= 40


# --- сборка/разбор MD ---


def test_draft_to_markdown_parse_roundtrip():
    draft = make_draft()
    extra = {"session_uid": "ses_1", "conversation_uid": None, "created": "2026-01-01", "version": 1}
    content = draft_to_markdown("blk_ab12cd34", draft, extra)

    meta, body = parse_markdown(content)

    assert meta["id"] == "blk_ab12cd34"
    assert meta["title"] == "Сетевая модель подов"
    assert meta["kind"] == "lesson"
    assert meta["summary"] == "CNI и pause-контейнер"
    assert meta["session"] == "ses_1"
    assert meta["tags"] == ["k8s", "net"]
    assert meta["sources"] == [{"source": "src_12345678", "chapter": 1, "title": "K8s Book"}]
    assert meta["category"] == "infra/kubernetes"
    assert meta["category_status"] == "suggested"

    assert "# Сетевая модель подов" in body
    assert "## Ключевые понятия" in body and "**Pod**" in body
    assert "## Тезисы" in body
    assert "## Как я это понял" in body
    assert "## Схема" in body and "```mermaid" in body and "graph TD" in body
    assert "## Практика" in body and "kubectl get pods" in body
    assert "## Дозакрепить" in body
    assert "## Вопросы на потом" in body
    assert "## Связи" in body and "[[blk_deadbeef]]" in body
    assert "## Источники" in body and "src_12345678#1" in body

    # ссылки вытаскиваются из тела
    assert extract_links(body) == ("blk_deadbeef",)


def test_parse_markdown_requires_frontmatter():
    with pytest.raises(ValueError, match="frontmatter"):
        parse_markdown("# просто заголовок без frontmatter")


def test_extract_links_only_block_uids():
    """Wikilink-регулярка берёт только blk_ + hex; текст и не-hex игнорируются."""
    body = "Связи: [[blk_00ff00ff]] и [[blk_11aa22bb]], но [[просто текст]] и [[blk_zz]] — мимо"
    assert extract_links(body) == ("blk_00ff00ff", "blk_11aa22bb")


# --- apply_patch ---


def test_apply_patch_replaces_lists_wholesale():
    draft = make_draft()
    patched = apply_patch(draft, {"theses": ["новый тезис"]})
    assert patched.theses == ("новый тезис",)
    # остальное не тронуто
    assert patched.concepts == draft.concepts


def test_apply_patch_append_operations():
    draft = make_draft()
    patched = apply_patch(
        draft,
        {
            "append_theses": ["ещё тезис"],
            "append_examples": ["новый пример"],
            "append_concepts": [{"term": "CNI", "definition": "сетевой плагин"}],
            "append_weak_spots": ["veth всё ещё загадка"],
        },
    )
    assert patched.theses == draft.theses + ("ещё тезис",)
    assert patched.my_examples == draft.my_examples + ("новый пример",)
    assert patched.concepts == draft.concepts + (Concept("CNI", "сетевой плагин"),)
    assert patched.weak_spots == draft.weak_spots + ("veth всё ещё загадка",)


def test_apply_patch_converts_nested_dicts():
    patched = apply_patch(
        make_draft(),
        {"practice": [{"machine": "homelab", "command": "pct list", "explanation": "контейнеры"}]},
    )
    assert patched.practice == (PracticeStep("homelab", "pct list", "контейнеры"),)


def test_apply_patch_empty_list_clears_field():
    patched = apply_patch(make_draft(), {"concepts": []})
    assert patched.concepts == ()


def test_apply_patch_unknown_field_raises():
    with pytest.raises(ValueError, match="неизвестное поле"):
        apply_patch(make_draft(), {"no_such_field": 1})


# --- категории ---


def test_category_ancestors_includes_path_itself():
    assert category_ancestors("programming/python/oop") == [
        "programming",
        "programming/python",
        "programming/python/oop",
    ]


def test_normalize_category_path():
    assert normalize_category_path(" / Infra / Kubernetes ") == "infra/kubernetes"
