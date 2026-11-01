"""R-12: слой контекста — карточки/трасса инструментов в истории, компактация, бюджет."""

from app.kernel.clock import now_iso
from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from tests.api.test_sse import parse_sse


def _post(client, uid: str, content: str) -> list:
    r = client.post(f"/api/conversations/{uid}/messages", json={"content": content})
    assert r.status_code == 200, r.text
    return parse_sse(r.text)


def _agent_system(fake_llm) -> str:
    """Системный промпт последнего агентского запроса (с инструментами)."""
    reqs = [r for r in fake_llm.requests if r[1].tools]
    return reqs[-1][1].messages[0].content


def test_tool_trace_reaches_next_turn_history(container, client, fake_llm):
    """Трасса инструментов хода сохраняется с ответом и видна агенту далее (R-12)."""
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("list_blocks")]),
        FakeTurn(text="Вот блоки"),
        FakeTurn(text="Помню, что показал"),
    )
    _post(client, conv["uid"], "что в базе?")
    _post(client, conv["uid"], "помнишь, что нашёл?")

    msgs = client.get(f"/api/conversations/{conv['uid']}").json()["messages"]
    with_trace = [m for m in msgs if m["role"] == "assistant" and m.get("tool_calls")]
    assert with_trace, "трасса инструментов не сохранилась с ответом"
    assert with_trace[0]["tool_calls"][0]["name"] == "list_blocks"

    # и трасса попала в историю следующего хода
    fake_llm.queue(FakeTurn(text="ок"))
    _post(client, conv["uid"], "ещё вопрос")
    system_context = " ".join(m.content for r in fake_llm.requests[-3:] if r[1].tools for m in r[1].messages)
    assert "инструменты: list_blocks(ок" in system_context


def test_cards_reach_next_turn_history(container, client, fake_llm):
    """Карточка ответа видна агенту на следующем ходу — резюме в истории (R-12)."""
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("offer_replies", replies=["Дальше", "Подробнее"])]),
        FakeTurn(text="Выбирай кнопкой"),
        FakeTurn(text="Продолжаю"),
    )
    _post(client, conv["uid"], "дальше?")
    _post(client, conv["uid"], "Дальше")

    fake_llm.queue(FakeTurn(text="ок"))
    _post(client, conv["uid"], "контроль")
    context = " ".join(m.content for r in fake_llm.requests[-3:] if r[1].tools for m in r[1].messages)
    assert "карточка quick_replies" in context


def _seed_long_history(container, conv: dict, turns: int = 10, chunk: str = "т" * 4000) -> None:
    """Длинная история напрямую в БД (без LLM): turns пар по ~4к символов."""
    with container.uow() as uow:
        for i in range(turns):
            container.chat._msgs.insert(  # noqa: SLF001
                uow.session,
                conversation_id=conv["id"],
                role="user",
                content=f"{chunk} вопрос {i}",
                created_at=now_iso(container.clock),
            )
            container.chat._msgs.insert(  # noqa: SLF001
                uow.session,
                conversation_id=conv["id"],
                role="assistant",
                content=f"{chunk} ответ {i}",
                created_at=now_iso(container.clock),
            )


def test_compaction_writes_summary_and_trims_history(container, client, fake_llm):
    """Переполнение бюджета → conversation_summarizer пишет summary в разговор (R-12)."""
    conv = client.post("/api/conversations", json={}).json()
    _seed_long_history(container, conv)

    fake_llm.queue(
        FakeTurn(text='{"summary": "Изучали Docker: главы 1–4 пройдены, конспект после главы 5."}')
    )
    _post(client, conv["uid"], "итак, продолжаем")

    detail = client.get(f"/api/conversations/{conv['uid']}").json()
    assert detail["summary"] and "Docker" in detail["summary"]

    # история следующего хода: сжатие + хвост, старые 4k-куски не тащатся целиком
    fake_llm.queue(FakeTurn(text="ок"))
    _post(client, conv["uid"], "проверка")
    last_req = [r for r in fake_llm.requests if r[1].tools][-1][1]
    joined = " ".join(m.content for m in last_req.messages)
    assert "Сжатая история разговора" in joined
    assert "ответ 0" not in joined  # старьё сжато, не в контексте


def test_no_compaction_below_budget(container, client, fake_llm):
    """Короткий разговор не дёргает summarizer."""
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(FakeTurn(text="привет"))
    _post(client, conv["uid"], "hi")
    assert client.get(f"/api/conversations/{conv['uid']}").json()["summary"] is None
