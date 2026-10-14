"""LLM-слой: FakeLLMProvider, structured_output (ретраи JSON), _extract_json."""

import pytest
from pydantic import BaseModel

from app.kernel.errors import LLMError
from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from app.llm.structured import _extract_json, structured_output
from app.llm.types import LLMRequest, Message


class Note(BaseModel):
    """Мини-модель для structured_output."""

    title: str
    tags: list[str] = []


def _messages() -> list[Message]:
    return [Message(role="user", content="сделай заметку")]


# --- FakeLLMProvider ---


async def test_fake_provider_returns_queued_turns_in_order():
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text="первый"), FakeTurn(text="второй"))
    r1 = await fake.complete("m", LLMRequest(messages=(Message(role="user", content="q"),)))
    r2 = await fake.complete("m", LLMRequest(messages=(Message(role="user", content="q"),)))
    assert (r1.text, r2.text) == ("первый", "второй")
    assert len(fake.requests) == 2


async def test_fake_provider_fallback_text_when_queue_empty():
    fake = FakeLLMProvider()
    r = await fake.complete("m", LLMRequest(messages=(Message(role="user", content="q"),)))
    assert "сценарий исчерпан" in r.text


async def test_fake_provider_raises_queued_error():
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(error=RuntimeError("провайдер лёг")))
    with pytest.raises(RuntimeError, match="провайдер лёг"):
        await fake.complete("m", LLMRequest(messages=(Message(role="user", content="q"),)))


async def test_fake_provider_stream_yields_words_and_finish():
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text="Привет мир"))
    events = [e async for e in fake.stream("m", LLMRequest(messages=(Message(role="user", content="q"),)))]
    texts = [e.text for e in events if e.type == "text"]
    # фейк отдаёт слово + пробел, поэтому в сумме — текст с хвостовым пробелом
    assert "".join(texts) == "Привет мир "
    assert events[-1].type == "finish" and events[-1].finish_reason == "stop"


# --- structured_output ---


async def test_structured_output_valid_json_first_attempt():
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text='{"title": "Заметка", "tags": ["a"]}'))
    out = await structured_output(fake, "m", _messages(), Note)
    assert isinstance(out, Note)
    assert out.title == "Заметка" and out.tags == ["a"]
    assert len(fake.requests) == 1


async def test_structured_output_retries_invalid_then_valid():
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text="это не JSON"), FakeTurn(text='{"title": "Со второй попытки"}'))
    out = await structured_output(fake, "m", _messages(), Note)
    assert out.title == "Со второй попытки"
    assert len(fake.requests) == 2
    # во второй запрос ушла подсказка об ошибке
    second = fake.requests[1][1]
    assert any("JSON невалиден" in m.content for m in second.messages)


async def test_structured_output_unwraps_fenced_json():
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text='Ответ:\n```json\n{"title": "Из забора"}\n```\nконец'))
    out = await structured_output(fake, "m", _messages(), Note)
    assert out.title == "Из забора"


async def test_structured_output_exhausts_attempts_and_raises():
    fake = FakeLLMProvider()
    fake.queue(*[FakeTurn(text="мусор") for _ in range(3)])
    with pytest.raises(LLMError, match="3 попыток"):
        await structured_output(fake, "m", _messages(), Note)
    assert len(fake.requests) == 3


# --- _extract_json ---


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_fenced():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_json_with_surrounding_text():
    assert _extract_json('Вот ответ: {"a": 1} — как просил') == '{"a": 1}'


def test_extract_json_empty_falls_back_to_empty_object():
    assert _extract_json("") == "{}"
    assert _extract_json("вообще не JSON") == "вообще не JSON"
