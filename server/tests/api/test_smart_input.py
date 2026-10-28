"""Умный вход (T-036): претрекер контента в system_extra, attachments-PDF, offer_action, скиллы."""

import io

import fitz

from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from tests.api.test_sse import parse_sse


def _make_pdf(title: str = "Книга вложения") -> bytes:
    """Минимальный валидный PDF с одной страницей."""
    doc = fitz.open()
    doc.new_page().insert_text((72, 96), title)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _system_prompt(fake_llm) -> str:
    """Системное сообщение первого запроса агента (профиль + pretreck-заметки)."""
    return fake_llm.requests[0][1].messages[0].content


def test_youtube_link_note_reaches_agent(client, fake_llm):
    """Сообщение с YouTube-ссылкой → агенту в system_extra уходит заметка с типом и действиями."""
    fake_llm.queue(FakeTurn(text="Предлагаю разобрать видео."), FakeTurn(text="видео"))
    conv = client.post("/api/conversations", json={}).json()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": f"посмотри {url}"}
    ) as resp:
        raw = "".join(resp.iter_text())

    assert [name for name, _ in parse_sse(raw)][-1] == "done"
    prompt = _system_prompt(fake_llm)
    assert f"YouTube-ссылка {url}" in prompt
    assert "add_source(kind=video" in prompt
    # текст сообщения агенту не режется и не меняется претрекером
    assert f"посмотри {url}" in fake_llm.requests[0][1].messages[-1].content


def test_attachment_pdf_creates_note_and_card(client, fake_llm, container):
    """Сообщение с attachments=[pdf]: источник создан до агента, uid и title — в заметке агенту,
    карточка-вложение сохранена на user-сообщении, ответ не падает."""
    fake_llm.queue(FakeTurn(text="Видел вложение."), FakeTurn(text="вложение"))
    src = client.post(
        "/api/sources/upload",
        files={"file": ("book.pdf", _make_pdf(), "application/pdf")},
        data={"title": "Книга вложения"},
    ).json()

    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST",
        f"/api/conversations/{conv['uid']}/messages",
        json={"content": "разбери приложенную книгу", "attachments": [{"source_uid": src["uid"]}]},
    ) as resp:
        raw = "".join(resp.iter_text())

    assert [name for name, _ in parse_sse(raw)][-1] == "done"
    prompt = _system_prompt(fake_llm)
    assert "Пользователь приложил PDF «Книга вложения»" in prompt
    assert f"uid={src['uid']}" in prompt
    assert "process_source" in prompt

    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    user_msg = next(m for m in fresh["messages"] if m["role"] == "user")
    assert user_msg["content"] == "разбери приложенную книгу"
    attach = [c for c in user_msg["cards"] if c["type"] == "attachment"]
    assert attach and attach[0]["source_uid"] == src["uid"]
    assert attach[0]["title"] == "Книга вложения"


def test_attachment_unknown_source_is_sse_error(client, fake_llm):
    """Вложение с несуществующим uid — сообщение не отправляется, ошибка уходит SSE-событием."""
    fake_llm.queue(FakeTurn(text="не дойдёт"))
    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST",
        f"/api/conversations/{conv['uid']}/messages",
        json={"content": "разбери", "attachments": [{"source_uid": "src_missing"}]},
    ) as resp:
        raw = "".join(resp.iter_text())
    events = parse_sse(raw)
    assert [name for name, _ in events] == ["error"]
    assert not fake_llm.requests  # агент не запускался


def test_skills_visible_to_root_and_free_chat(container):
    """RESEARCH_DIRECTIVE обещает torrent_fetch — инструменты скиллов выданы root и free_chat."""
    for agent in ("root", "free_chat"):
        tools = set(container.agent_registry.get(agent).tools)
        assert {"run_skill", "list_skills", "torrent_fetch"} <= tools
    # сами инструменты зарегистрированы и callable
    from app.kernel.tools.spec import ToolContext

    out = container.tools.call("list_skills", {}, ToolContext(channel="mcp"))
    assert "torrent_fetch" in {s["name"] for s in out}


def test_offer_action_card_streamed_and_saved(client, fake_llm):
    """Агент зовёт offer_action → карточка действия уходит в SSE и сохраняется в сообщении."""
    fake_llm.queue(
        FakeTurn(
            tool_calls=[
                FakeLLMProvider.call(
                    "offer_action", title="Добавить видео в Библиотеку?", description="Скачаю транскрипт"
                )
            ]
        ),
        FakeTurn(text="Жду твоего решения."),
        FakeTurn(text="предложение"),
    )
    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "вот видео"}
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    cards = [d["card"] for name, d in events if name == "card"]
    offer = next(c for c in cards if c["type"] == "action_offer")
    assert offer["title"] == "Добавить видео в Библиотеку?"
    assert offer["description"] == "Скачаю транскрипт"

    fresh = client.get(f"/api/conversations/{conv['uid']}").json()
    assistant = next(m for m in fresh["messages"] if m["role"] == "assistant")
    assert any(c["type"] == "action_offer" for c in assistant["cards"])
