"""R-19: поиск прощает естественную речь — OR+bm25, префиксы, стоп-слова, инкремент."""

from app.modules.search.infra.fts import fts_query


def test_fts_query_or_with_prefixes_and_stop_words():
    q = fts_query("Как работают контейнеры в кубере?")
    assert q == '"работают"* OR "контейнеры"* OR "кубере"*'  # как/в — стоп-слова


def test_fts_query_short_words_exact():
    assert fts_query("go ru") == '"go" OR "ru"'  # <3 символов — без префикса


def test_fts_query_empty_falls_back_to_neutral():
    assert fts_query("и в на") == '""'


def _seed_blocks(container) -> None:
    from app.modules.knowledge.domain import BlockDraft

    container.knowledge.save_block(
        BlockDraft(
            title="Поды Kubernetes",
            summary="контейнеры в подах",
            theses=("под = один или несколько контейнеров",),
            category_suggestion="infra/kubernetes",
            tags=("k8s",),
        ),
        category_status="confirmed",
    )
    container.knowledge.save_block(
        BlockDraft(
            title="Готовка борща",
            summary="классика",
            theses=("свёкла обязательна",),
            category_suggestion="life/cooking",
        ),
        category_status="confirmed",
    )


def test_natural_language_query_finds_morphology(container, client):
    """«как работают поды» находит блок — раньше AND по точным токенам давал 0 (R-19)."""
    _seed_blocks(container)
    out = client.get("/api/search", params={"q": "как работают поды"}).json()
    blocks = out.get("blocks") or []
    assert any("Kubernetes" in (b.get("title") or "") for b in blocks)


def test_plural_prefix_match(container, client):
    """Префикс «контейнер» ловит «контейнеров» в тексте (морфология без стеммера, R-19)."""
    _seed_blocks(container)
    out = client.get("/api/search", params={"q": "контейнер"}).json()
    assert any("Kubernetes" in (b.get("title") or "") for b in (out.get("blocks") or []))


def test_ranking_relevant_first(container, client):
    _seed_blocks(container)
    out = client.get("/api/search", params={"q": "борщ свёкла"}).json()
    blocks = out.get("blocks") or []
    assert blocks and "борщ" in (blocks[0].get("title") or "").lower()


def test_category_searchable(container, client):
    """Категория в индексе: «kubernetes» находит блок ветки (R-19)."""
    _seed_blocks(container)
    out = client.get("/api/search", params={"q": "kubernetes"}).json()
    assert any("Поды" in (b.get("title") or "") for b in (out.get("blocks") or []))
