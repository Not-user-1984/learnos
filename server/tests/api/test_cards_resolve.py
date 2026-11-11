"""Resolve карточек-решений (B-003): слияние групп решений за ход, статус в БД, идемпотентность."""

import json

from app.llm.providers.fake import FakeLLMProvider, FakeTurn

from .test_sse import parse_sse


def _run_turns(client, fake_llm, uid, turns):
    fake_llm.queue(*turns)
    with client.stream("POST", f"/api/conversations/{uid}/messages", json={"content": "вопрос"}) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    return parse_sse(raw)


def test_two_decision_cards_merge_into_one(client, fake_llm):
    """offer_action + offer_replies в одном ходе — одна карточка с общими вариантами."""
    turns = [
        FakeTurn(
            tool_calls=[
                FakeLLMProvider.call("offer_action", title="Добавить видео?", description="в Библиотеку"),
                FakeLLMProvider.call("offer_replies", replies=["Дальше", "Подробнее"]),
            ]
        ),
        FakeTurn(text="готово"),
    ]
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    events = _run_turns(client, fake_llm, conv["uid"], turns)

    # обе карточки пришли событием card, но вторая — заменой первой (index=0)
    card_events = [data for name, data in events if name == "card"]
    assert len(card_events) == 2
    assert card_events[0]["index"] == 0
    assert card_events[1]["index"] == 0
    labels = [o["label"] for o in card_events[1]["card"]["options"]]
    assert labels == ["Да", "Нет", "Дальше", "Подробнее"]

    # в сохранённом сообщении — одна карточка-решение с общими вариантами и card_id
    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    assistant = [m for m in fresh["messages"] if m["role"] == "assistant"][-1]
    decisions = [c for c in assistant["cards"] if c["type"] in {"action_offer", "quick_replies"}]
    assert len(decisions) == 1
    assert decisions[0]["card_id"]
    assert [o["label"] for o in decisions[0]["options"]] == ["Да", "Нет", "Дальше", "Подробнее"]


def test_resolve_idempotent_and_conflict(client, fake_llm):
    """Resolve: повтор с тем же choice — 200, с другим — 409; статус виден в истории."""
    turns = [
        FakeTurn(tool_calls=[FakeLLMProvider.call("offer_action", title="Скачать книгу?")]),
        FakeTurn(text="жду решения"),
    ]
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    _run_turns(client, fake_llm, conv["uid"], turns)

    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    card = next(c for m in fresh["messages"] for c in m["cards"] if c["type"] == "action_offer")
    url = f"/api/conversations/{conv['uid']}/cards/{card['card_id']}/resolve"

    first = client.post(url, json={"choice": "Да"})
    assert first.status_code == 200
    assert first.json()["status"] == "resolved"
    assert first.json()["choice"] == "Да"

    again = client.post(url, json={"choice": "Да"})
    assert again.status_code == 200
    assert again.json()["choice"] == "Да"

    other = client.post(url, json={"choice": "Нет"})
    assert other.status_code == 409

    # статус переживает перечитывание истории
    fresh2 = client.get(f"/api/conversations/{conv['uid']}").json()
    card2 = next(c for m in fresh2["messages"] for c in m["cards"] if c["card_id"] == card["card_id"])
    assert card2["status"] == "resolved"
    assert card2["choice"] == "Да"


def test_resolve_unknown_card_404(client):
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    r = client.post(f"/api/conversations/{conv['uid']}/cards/m0c0/resolve", json={"choice": "Да"})
    assert r.status_code == 404


def test_legacy_cards_get_ids_and_resolvable(client, fake_llm):
    """Карточкам старых сообщений (без card_id) id выдаётся детерминированно, resolve работает."""
    turns = [
        FakeTurn(tool_calls=[FakeLLMProvider.call("offer_replies", replies=["Ага", "Неа"])]),
        FakeTurn(text="вопрос задан"),
    ]
    conv = client.post("/api/conversations", json={"mode": "free"}).json()
    _run_turns(client, fake_llm, conv["uid"], turns)

    # затираем card_id, имитируя старое сообщение
    from app.modules.chat.infra.tables import messages as messages_table

    container = client.app.state.container
    with container.uow() as uow:
        row = uow.session.execute(messages_table.select().order_by(messages_table.c.id.desc())).first()
        cards = [dict(c) for c in json.loads(row.cards_json)]
        for c in cards:
            c.pop("card_id", None)
        uow.session.execute(
            messages_table.update()
            .where(messages_table.c.id == row.id)
            .values(cards_json=json.dumps(cards, ensure_ascii=False))
        )

    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    card = next(c for m in fresh["messages"] for c in m["cards"] if c["type"] == "quick_replies")
    assert card["card_id"]  # id сгенерирован на лету
    r = client.post(
        f"/api/conversations/{conv['uid']}/cards/{card['card_id']}/resolve", json={"choice": "Ага"}
    )
    assert r.status_code == 200
    assert r.json()["choice"] == "Ага"
