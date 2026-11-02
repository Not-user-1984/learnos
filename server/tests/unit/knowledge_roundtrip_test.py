"""R-02: правка блока не должна терять секции, размножать «Дозакрепить» и сбрасывать статус.

Round-trip: save_block → update_block → файл содержит всё, что был до правки;
reindex не возвращает подтверждённый блок во «Входящие».
"""

from app.modules.knowledge.domain import (
    BlockDraft,
    BlockSource,
    Concept,
    PracticeStep,
    parse_markdown,
)


def rich_draft() -> BlockDraft:
    """Драфт со всеми секциями, которые раньше терялись при правке."""
    return BlockDraft(
        title="Сетевая модель подов",
        summary="Как под общается с сетью",
        kind="lesson",
        concepts=(
            Concept(term="под", definition="минимальная единица деплоя в Kubernetes"),
            Concept(term="CNI", definition="плагин, дающий поду IP-адрес"),
        ),
        theses=("kubelet создаёт sandbox",),
        my_examples=("как в моём хомлабе traffic шёл мимо CNI",),
        mermaid='flowchart LR\n  A["Pod"] --> B["CNI"]',
        practice=(
            PracticeStep(
                machine="pve",
                command="kubectl get pods -A",
                explanation="посмотреть все поды",
                result="42 пода",
            ),
            PracticeStep(
                machine="mac",
                command="ping 10.42.0.1",
                explanation="проверить доступность pod CIDR",
                verify="ответ есть",
                cleanup=None,
            ),
        ),
        weak_spots=("разница hostNetwork и hostPort", "где живёт SNAT"),
        open_questions=("как устроен conntrack в Calico",),
        links=(),
        tags=("k8s", "network"),
        category_suggestion="infra/kubernetes",
        sources=(BlockSource(source="src_test0001", chapter=3, title="K8s Book"),),
    )


def test_draft_roundtrip_render_parse_no_loss(container):
    """Рендер → разбор возвращают тот же драфт (секции, практика, weak_spots)."""
    draft = rich_draft()
    meta = {
        "session_uid": None,
        "conversation_uid": None,
        "activity_uid": None,
        "created": "2026-11-01T00:00:00",
        "updated": "2026-11-01T00:00:00",
        "version": 1,
        "category_status": "confirmed",
    }
    from app.modules.knowledge.domain import draft_to_markdown

    content = draft_to_markdown("blk_roundtrip1", draft, meta)
    meta_raw, _body = parse_markdown(content)
    parsed = container.knowledge._draft_from_frontmatter(meta_raw, content)  # noqa: SLF001

    assert parsed.title == draft.title
    assert parsed.concepts == draft.concepts
    assert parsed.practice == draft.practice
    assert parsed.weak_spots == draft.weak_spots
    assert parsed.theses == draft.theses
    assert parsed.my_examples == draft.my_examples
    assert parsed.open_questions == draft.open_questions
    assert parsed.mermaid == draft.mermaid
    assert parsed.tags == draft.tags
    assert parsed.sources == draft.sources


def test_update_block_keeps_sections_and_status(container):
    """append_theses не стирает concepts/practice, не множит weak_spots, статусConfirmed живёт."""
    k = container.knowledge
    block = k.save_block(rich_draft(), category_status="confirmed")
    uid = block.meta.uid

    k.update_block(uid, {"append_theses": ["новый тезис"]}, reason="правка из разговора")
    after = k.get_block(uid)

    # concepts и практика на месте
    assert "- **под** — минимальная единица деплоя в Kubernetes" in after.content
    assert "**pve** · `kubectl get pods -A`" in after.content
    assert "; результат: 42 пода" in after.content
    assert "; проверка: ответ есть" in after.content
    assert "новый тезис" in after.content
    # weak_spots не размножились
    assert after.meta.weak_spots_count == 2
    assert after.meta.category_status == "confirmed"

    # вторая правка — счётчик стабилен (callout-мусор не плодится)
    k.update_block(uid, {"append_theses": ["ещё тезис"]}, reason="вторая правка")
    again = k.get_block(uid)
    assert again.meta.weak_spots_count == 2
    assert " [!WARNING]" not in " ".join(
        line for line in again.content.splitlines() if not line.startswith("> [!WARNING]")
    )


def test_reindex_keeps_confirmed_status_after_update(container):
    """reindex читает файл: подтверждённая категория не сбрасывается во «Входящие» (R-02.3)."""
    k = container.knowledge
    block = k.save_block(rich_draft(), category_status="confirmed")
    uid = block.meta.uid
    k.update_block(uid, {"append_theses": ["тезис"]}, reason="правка")

    result = k.reindex()
    assert result["updated"] >= 1
    after = k.get_block(uid)
    assert after.meta.category_status == "confirmed"
    assert k.inbox() == []


def test_update_block_survives_legacy_callouts_without_blank_line(container):
    """Старые файлы (callout'ы слитые, без пустых строк) разбираются без пункта-мусора."""
    k = container.knowledge
    block = k.save_block(rich_draft(), category_status="confirmed")
    uid = block.meta.uid
    # сымитируем старый рендер: склеим callout'ы без пустой строки между ними
    content = k._files.read(block.meta.path)  # noqa: SLF001
    legacy = content.replace(
        "> [!WARNING]\n> разница hostNetwork и hostPort\n\n",
        "> [!WARNING]\n> разница hostNetwork и hostPort\n",
    )
    k._files.write_raw(block.meta.path, legacy)  # noqa: SLF001

    updated = k.update_block(uid, {"append_theses": ["тезис"]}, reason="правка legacy")
    assert updated.meta.weak_spots_count == 2
    assert "[!WARNING]" not in "\n".join(
        line[2:]
        for line in updated.content.splitlines()
        if line.startswith("> ") and "[!WARNING]" not in line
    )


def test_review_state_survives_update(container):
    """SRS-состояние в frontmatter не сбрасывается на дефолт при пересборке файла."""
    k = container.knowledge
    block = k.save_block(rich_draft(), category_status="confirmed")
    uid = block.meta.uid
    content = k._files.read(block.meta.path)  # noqa: SLF001
    meta_raw, body = parse_markdown(content)
    meta_raw["review"] = {"ease": 2.9, "interval": 12, "due": "2026-12-01"}
    from app.modules.knowledge.service import _assemble

    k._files.write_raw(block.meta.path, _assemble(meta_raw, body))  # noqa: SLF001

    updated = k.update_block(uid, {"append_theses": ["тезис"]}, reason="правка")
    content2 = k._files.read(updated.meta.path)  # noqa: SLF001
    meta2, _ = parse_markdown(content2)
    assert meta2["review"] == {"ease": 2.9, "interval": 12, "due": "2026-12-01"}


def test_categories_yaml_restored_from_db_when_file_lost(container):
    """Файл категорий пропал (чистый сброс данных) — восстанавливается из БД (T-052)."""
    from app.modules.knowledge.infra.md_store import MdBlockStore

    k = container.knowledge
    yaml_path = MdBlockStore(container.settings.kb_dir).blocks_dir.parent / "categories.yaml"
    yaml_path.write_text("", encoding="utf-8")
    yaml_path.unlink()

    k.ensure_categories_default()
    assert yaml_path.exists()
    content = yaml_path.read_text(encoding="utf-8")
    assert "infra" in content and "programming" in content
