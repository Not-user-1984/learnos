"""B-014: карточки-суть — генерация, SM-2 на карточку, фильтр по источнику."""

import json

from app.kernel.errors import NotFound
from app.llm.providers.fake import FakeTurn
from app.modules.knowledge.domain import BlockDraft, BlockSource, Card


def _save_block(container, title: str, sources=(), cards=()) -> str:
    draft = BlockDraft(title=title, theses=("тезис",), sources=sources, cards=cards)
    return container.knowledge.save_block(draft).meta.uid


def _writer_turn(n_cards: int = 3) -> FakeTurn:
    return FakeTurn(
        text=json.dumps(
            {
                "title": "Блок с карточками",
                "summary": "с",
                "theses": ["тезис"],
                "concepts": [],
                "practice": [],
                "weak_spots": [],
                "open_questions": [],
                "links": [],
                "tags": [],
                "category_suggestion": None,
                "sources": [],
                "cards": [
                    {"q": f"Вопрос номер {i} про суть?", "a": f"Короткий ответ {i}. Одна-две мысли."}
                    for i in range(1, n_cards + 1)
                ],
            },
            ensure_ascii=False,
        )
    )


# --- генерация при создании блока (block_writer с карточками) ---


def test_block_writer_cards_limited_and_get_ids(container, fake_llm):
    """Карточки из block_writer попадают в блок: ≤5, с устойчивыми id."""
    fake_llm.queue(_writer_turn(3))
    draft = container.knowledge.generate_from_dialog("диалог")
    block = container.knowledge.save_block(draft)
    assert [c.id for c in block.meta.cards] == ["c1", "c2", "c3"]
    assert all(len(c.a) < 200 for c in block.meta.cards)
    # карточки видны в API
    meta = container.knowledge.get_block(block.meta.uid).meta
    assert len(meta.cards) == 3 and meta.cards[0].q.startswith("Вопрос")


def test_make_cards_for_old_block(container, fake_llm):
    """«Сделать карточки» на старом блоке: card_writer → frontmatter, версия растёт."""
    uid = _save_block(container, "Старый блок")
    assert container.knowledge.get_block(uid).meta.cards == ()

    fake_llm.queue(
        FakeTurn(
            text=json.dumps(
                {
                    "cards": [
                        {"q": "Что делает X?", "a": "X делает одно."},
                        {"q": "Чем Y отличается?", "a": "Y — другое."},
                        {"q": "Когда звать Z?", "a": "Z зовут после X."},
                    ]
                },
                ensure_ascii=False,
            )
        )
    )
    out = container.knowledge.make_cards(uid)
    assert out["ok"] and len(out["cards"]) == 3
    assert [c["id"] for c in out["cards"]] == ["c1", "c2", "c3"]
    assert out["version"] == 2  # правка блока = новая версия

    # карточки в MD frontmatter
    content = container.knowledge.get_block(uid).content
    assert "cards:" in content and "Что делает X?" in content


def test_cards_edit_keeps_ids_and_version(container):
    """Правка карточек на странице блока: id сохранённых устойчивы, версия растёт."""
    uid = _save_block(
        container,
        "Блок с правкой",
        cards=(Card("", "Вопрос один?", "Ответ один."), Card("", "Вопрос два?", "Ответ два.")),
    )
    before = container.knowledge.get_block(uid).meta
    assert [c.id for c in before.cards] == ["c1", "c2"]

    updated = container.knowledge.update_block(
        uid,
        {
            "cards": [
                {"id": "c2", "q": "Вопрос два (правка)?", "a": "Ответ два."},
                {"q": "Совершенно новый вопрос?", "a": "Новый ответ."},
            ]
        },
        "правка карточек",
    )
    ids = [c.id for c in updated.meta.cards]
    assert ids == ["c2", "c3"]  # c2 сохранён, новой достался следующий свободный
    assert updated.meta.version == 2


# --- SM-2 на карточку ---


def test_answer_card_moves_due_by_grade(client, container):
    """«Не помню/Трудно/Помню» → SM-2: срок карточки сдвигается по оценке."""
    uid = _save_block(container, "Карточный блок", cards=(Card("", "Q1?", "A1."), Card("", "Q2?", "A2.")))
    out = client.get("/api/review/queue?limit=10").json()
    cards = [i for i in out if i["kind"] == "card"]
    assert len(cards) == 2 and cards[0]["q"] == "Q1?"

    resp = client.post(
        "/api/review/answer-card",
        json={"block_uid": uid, "card_id": "c1", "grade": "good"},
    ).json()
    assert resp["ok"] and resp["interval_days"] >= 1

    fresh = [i for i in client.get("/api/review/queue?limit=10").json() if i.get("card_id") == "c1"]
    assert fresh == []  # ответ «помню» — карточка ушла из «на сегодня»

    again = client.post(
        "/api/review/answer-card",
        json={"block_uid": uid, "card_id": "c2", "grade": "again"},
    ).json()
    assert again["interval_days"] == 1  # провал: интервал сброшен

    with_not = client.post(
        "/api/review/answer-card",
        json={"block_uid": uid, "card_id": "c1", "grade": "mega"},
    )
    assert with_not.status_code == 404


def test_block_without_cards_stays_block_item(client, container):
    """Блок без карточек повторяется как раньше — одним блоковым элементом."""
    _save_block(container, "Блок без карточек")
    out = client.get("/api/review/queue?limit=10").json()
    assert any(i["kind"] == "block" for i in out) and not any(i.get("q") for i in out)


def test_cards_block_drops_block_item(client, container):
    """Появились карточки — блоковый элемент уступает место карточным."""
    uid = _save_block(container, "Станет карточным")
    out = client.get("/api/review/queue?limit=10").json()
    assert any(i["kind"] == "block" and i["block_uid"] == uid for i in out)

    container.knowledge.update_block(
        uid, {"cards": [{"q": "Новый вопрос?", "a": "Новый ответ."}]}, "появились карточки"
    )
    out = client.get("/api/review/queue?limit=10").json()
    assert not any(i["kind"] == "block" and i["block_uid"] == uid for i in out)
    assert any(i["kind"] == "card" and i["block_uid"] == uid for i in out)


# --- фильтр по источнику («Закрепить книгу») ---


def test_queue_filter_by_source(client, container):
    """?source= — только элементы блоков этого источника."""
    src = container.library.add_source("book", "Книга фильтра", url=None)
    mine = _save_block(
        container,
        "Из книги",
        sources=(BlockSource(source=src["uid"], chapter=2, title="Книга"),),
        cards=(Card("", "Q?", "A."),),
    )
    other = _save_block(container, "Не из книги")
    del other

    out = client.get(f"/api/review/queue?limit=10&source={src['uid']}").json()
    assert out and all(i["block_uid"] == mine for i in out)

    stats = client.get(f"/api/review/stats?source={src['uid']}").json()
    assert stats["total"] == 1


# --- миграция и целостность ---


def test_unknown_card_answer_rejected(client, container):
    """Оценка несуществующей карточки — 404, без побочных эффектов."""
    uid = _save_block(container, "Одинокая карточка", cards=(Card("", "Q?", "A."),))
    resp = client.post(
        "/api/review/answer-card",
        json={"block_uid": uid, "card_id": "c99", "grade": "good"},
    )
    assert resp.status_code == 404
    try:
        container.review.answer_card(uid, "c99", "good")
        raise AssertionError("должен был упасть NotFound")
    except NotFound:
        pass
