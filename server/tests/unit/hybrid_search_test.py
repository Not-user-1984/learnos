"""B-008: гибридный поиск — RRF, деградация в FTS, инкрементальность, удаление, качество топ-5."""

from app.modules.knowledge.domain import BlockDraft
from app.modules.search.service import chunk_text, rrf_fuse

# пары «запрос → ожидаемый блок»: общие слова дают совпадение и FTS, и фейк-вектору
RELEVANCE_PAIRS = [
    ("как не потерять данные при сбое", "WAL и надёжность записи"),
    ("оркестрация контейнеров кластером", "Kubernetes управление подами"),
    ("сетевые политики трафик", "Сетевые политики kubernetes"),
    ("хранилища тома диск", "Persistent volumes хранилище"),
    ("ci cd конвейер сборка", "GitOps конвейер ci cd"),
    ("наблюдаемость метрики логи", "Observability стек метрики"),
    ("безопасность секреты токены", "Секреты и безопасность кластера"),
    ("масштабирование реплик", "Автоскейлинг реплик подов"),
    ("базы данных транзакции", "Транзакции в postgres базах"),
    ("резервные копии восстановление", "Бэкапы и восстановление данных"),
]


def _seed_relevance_blocks(container) -> dict[str, str]:
    """10 блоков-дистракторов + 10 целевых; возвращает запрос → uid."""
    distractors = [
        "Рецепт борща со свёклой и капустой",
        "История Римской империи кратко",
        "Как выбрать велосипед для города",
        "Основы акварели и смешивания красок",
        "Программа тренировок на неделю",
        "Сборка кубика рубика за минуту",
        "Гид по тропическим рыбкам",
        "Обзор настольных игр для компании",
        "Учебник шахматных дебютов",
        "Путеводитель по горным маршрутам",
    ]
    for title in distractors:
        container.knowledge.save_block(BlockDraft(title=title, kind="note", theses=(title,)))
    mapping = {}
    for query, title in RELEVANCE_PAIRS:
        block = container.knowledge.save_block(
            BlockDraft(title=title, summary=title.lower(), kind="note", theses=(title,))
        )
        mapping[query] = block.meta.uid
    return mapping


def test_rrf_fuse_synthetic():
    """RRF: элемент из обоих списков побеждает; порядок устойчив."""
    fused = rrf_fuse([["a", "b", "c"], ["b", "d"]], limit=4)
    keys = [k for k, _ in fused]
    assert keys[0] == "b"  # встретился в обоих ранжированиях
    assert set(keys) == {"b", "a", "c", "d"}


def test_chunk_text_boundaries():
    chunks = chunk_text("Предложение раз. " * 200)  # ~3600 символов
    assert len(chunks) >= 3
    assert all(len(c) <= 2200 for c in chunks)


def test_search_degrades_to_fts_without_embed(container):
    """Router=None (роли нет) — hybrid не падает, FTS-результаты на месте."""
    from app.modules.search.infra.fts import FtsRepo
    from app.modules.search.service import SearchService

    svc = SearchService(container.uow, FtsRepo(), container.knowledge, vec=None, router=None)
    container.knowledge.save_block(
        BlockDraft(title="Kubernetes ingress", summary="ingress", kind="note", theses=("ingress",))
    )
    svc.reindex_blocks()
    out = svc.search("ingress", scope="blocks", mode="hybrid")
    assert out["blocks"] and out["blocks"][0]["block_uid"]


def test_index_incremental_and_delete(container):
    """Повторная индексация без изменений — skip; удаление блока чистит векторы."""
    block = container.knowledge.save_block(
        BlockDraft(title="Инкрементальность", kind="note", theses=("текст чанка один",))
    )
    uid = block.meta.uid
    first = container.search.index_block_embeddings(uid)
    assert first.get("indexed") is True
    second = container.search.index_block_embeddings(uid)
    assert second.get("skipped") is True and "не менялся" in second["reason"]

    status = container.search.vector_status()
    assert status["indexed_items"] >= 1

    container.search.on_block_deleted(uid)
    assert container.search.vector_status()["indexed_items"] == 0


def test_hybrid_finds_expected_blocks_top5(container):
    """≥10 пар: hybrid находит ожидаемый блок в топ-5 (фейковые bag-of-words векторы)."""
    mapping = _seed_relevance_blocks(container)
    container.search.reindex_blocks()
    for uid in set(mapping.values()):
        container.search.index_block_embeddings(uid)

    hits = 0
    for query, expected_uid in mapping.items():
        out = container.search.search(query, scope="blocks", limit=5, mode="hybrid")
        top5 = [b["block_uid"] for b in out["blocks"][:5]]
        if expected_uid in top5:
            hits += 1
    assert hits >= 8, f"hybrid нашёл только {hits}/10 в топ-5"


def test_vector_mode_finds_by_words(container):
    """mode=vector: bag-of-words вектор находит блок с общими словами."""
    block = container.knowledge.save_block(
        BlockDraft(
            title="Проверка векторного режима",
            summary="vector mode test",
            kind="note",
            theses=("уникальные слова зебра кварц",),
        )
    )
    container.search.index_block_embeddings(block.meta.uid)
    out = container.search.search("зебра кварц", scope="blocks", limit=3, mode="vector")
    assert any(b["block_uid"] == block.meta.uid for b in out["blocks"])
