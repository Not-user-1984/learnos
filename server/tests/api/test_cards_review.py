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


# --- раунд 2: замечания ревью B-014 ---


def test_patch_block_validates_cards(client, container):
    """PATCH с невалидной карточкой → 422, блок не меняется (fix п.1)."""
    uid = _save_block(container, "Валидация PATCH")
    base_version = container.knowledge.get_block(uid).meta.version

    bad = client.patch(
        f"/api/kb/blocks/{uid}",
        json={"cards": [{"q": "мало", "a": "ответ"}], "reason": "тест"},
    )
    assert bad.status_code == 422
    unknown = client.patch(
        f"/api/kb/blocks/{uid}",
        json={"cards": [], "unexpected": 1, "reason": "тест"},
    )
    assert unknown.status_code == 422

    dup = client.patch(
        f"/api/kb/blocks/{uid}",
        json={"cards": [{"id": "c1", "q": "Вопрос один?", "a": "Ответ."}] * 2, "reason": "тест"},
    )
    assert dup.status_code in (409, 422)  # дубли id — ValidationFailed

    assert container.knowledge.get_block(uid).meta.version == base_version  # блок не тронут


def test_patch_block_ok_path(client, container):
    """Валидный PATCH меняет карточки и возвращает карточки в ответе (fix п.1)."""
    uid = _save_block(container, "Валидный PATCH")
    ok = client.patch(
        f"/api/kb/blocks/{uid}",
        json={"cards": [{"q": "Новый вопрос карточки?", "a": "Новый ответ."}], "reason": "тест"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert [c["id"] for c in body["cards"]] == ["c1"]
    assert body["cards"][0]["q"].startswith("Новый вопрос")


def test_llm_six_cards_truncated_to_five(container, fake_llm):
    """6 карточек от LLM → 5 в блоке, блок не падает; 2 → тоже не падает (fix п.3)."""
    fake_llm.queue(_writer_turn(6))
    draft = container.knowledge.generate_from_dialog("диалог")
    block = container.knowledge.save_block(draft)
    assert len(block.meta.cards) == 5

    uid = _save_block(container, "Маленький блок для карточек")
    fake_llm.queue(
        FakeTurn(
            text=json.dumps(
                {"cards": [{"q": "Один-единственный вопрос по блоку?", "a": "Короткий ответ."}]},
                ensure_ascii=False,
            )
        )
    )
    out = container.knowledge.make_cards(uid)
    assert len(out["cards"]) == 1  # маленький блок — не фейл


def test_card_fixture_shape(container, fake_llm):
    """Карточки из фикстуры: ответ ≤280 символов и ≤2 предложения (fix п.7)."""
    fake_llm.queue(_writer_turn(4))
    draft = container.knowledge.generate_from_dialog("диалог")
    for c in draft.cards:
        assert len(c.a) <= 280
        assert c.a.count(".") <= 2 or len(c.a) < 200


def test_card_deletion_cleans_review_item(client, container):
    """Удаление карточки чистит её review_card_items (fix п.4)."""
    uid = _save_block(
        container,
        "Чистка элементов",
        cards=(Card("", "Q1?", "A1."), Card("", "Q2?", "A2.")),
    )
    client.get("/api/review/queue?limit=10")  # ensure завёл элементы обеим
    with container.uow() as uow:
        from app.modules.review.infra.tables import review_card_items as rci

        ids = uow.session.execute(rci.select().where(rci.c.block_uid == uid)).fetchall()
    assert {r.card_id for r in ids} == {"c1", "c2"}

    container.knowledge.update_block(uid, {"cards": [{"id": "c1", "q": "Q1?", "a": "A1."}]}, "удалил c2")
    with container.uow() as uow:
        from app.modules.review.infra.tables import review_card_items as rci

        ids = uow.session.execute(rci.select().where(rci.c.block_uid == uid)).fetchall()
    assert {r.card_id for r in ids} == {"c1"}


def test_block_delete_cleans_review_items(client, container):
    """DELETE блока чистит карточные и блочный элементы повторений (fix п.4)."""
    uid = _save_block(container, "Удаляемый", cards=(Card("", "Q?", "A."),))
    plain = _save_block(container, "Удаляемый без карточек")
    client.get("/api/review/queue?limit=10")
    assert client.delete(f"/api/kb/blocks/{uid}").status_code in (200, 204)
    assert client.delete(f"/api/kb/blocks/{plain}").status_code in (200, 204)

    with container.uow() as uow:
        from app.modules.review.infra.tables import review_card_items as rci
        from app.modules.review.infra.tables import review_items as ri

        assert uow.session.execute(rci.select().where(rci.c.block_uid.in_([uid, plain]))).fetchall() == []
        assert uow.session.execute(ri.select().where(ri.c.block_uid.in_([uid, plain]))).fetchall() == []


def test_answer_on_card_block_requires_card_id(client, container, fake_llm):
    """Проговор карточного блока без card_id — отказ; с card_id — SM-2 карточки (fix п.5)."""
    uid = _save_block(container, "Карточный проговор", cards=(Card("", "Q?", "A."),))
    resp = client.post("/api/conversations", json={"mode": "free"})  # не нужен — прямой вызов сервиса ниже
    del resp
    try:
        container.review.answer(uid, "мой ответ")
        raise AssertionError("должен был упасть InvalidState")
    except Exception as e:  # noqa: BLE001 — InvalidState из kernel
        assert "card_id" in str(e)

    fake_llm.queue(FakeTurn(text=json.dumps({"quality": 4, "feedback": "хорошо"})))
    out = container.review.answer(uid, "мой ответ по карточке", card_id="c1")
    assert out["card_id"] == "c1" and out["interval_days"] >= 1
    # блочный элемент не появился (анти-пинг-понг с ensure_items)
    client.get("/api/review/queue?limit=10")
    with container.uow() as uow:
        from app.modules.review.infra.tables import review_items as ri

        assert uow.session.execute(ri.select().where(ri.c.block_uid == uid)).fetchall() == []
