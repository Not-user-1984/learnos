"""AgentRuntime: цикл «модель → инструменты → модель», события, отмена, трейсинг."""

from pathlib import Path

import pytest
from jinja2 import UndefinedError
from pydantic import BaseModel

from app.agent.runtime import AgentRuntime, NullRecorder, render_prompt
from app.agent.spec import AgentContext, AgentSpec, CancellationToken
from app.kernel.tools.registry import ToolRegistry
from app.kernel.tools.spec import ToolContext, ToolSpec
from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from app.llm.router import LLMConfig, ModelRouter
from app.llm.types import Message


class EchoArgs(BaseModel):
    """Аргументы тестового инструмента echo."""

    text: str


class Out(BaseModel):
    """Модель выхода для run_structured."""

    answer: str


class ListRecorder:
    """Рекордер, запоминающий все запуски (вместо записи в agent_runs)."""

    def __init__(self) -> None:
        self.runs: list[dict] = []

    def record(self, **kwargs) -> int:
        self.runs.append(kwargs)
        return len(self.runs)


def make_tools() -> ToolRegistry:
    """Реестр с одним инструментом echo, возвращающим _card."""
    registry = ToolRegistry()

    def echo(args: EchoArgs, ctx: ToolContext) -> dict:
        del ctx
        return {"ok": True, "echo": args.text, "_card": {"type": "echo", "text": args.text}}

    registry.register(
        ToolSpec(
            name="echo", module="test", description="эхо", args_model=EchoArgs, handler=echo, label="Эхо"
        )
    )
    return registry


def make_router(fake: FakeLLMProvider) -> ModelRouter:
    """Роутер, всегда выдающий фейковый провайдер для любой роли."""
    return ModelRouter(LLMConfig(providers={}, roles={}), force_provider=fake)


def make_spec(tmp_path: Path, *, tools=frozenset({"echo"}), max_steps: int = 4) -> AgentSpec:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Ты тестовый агент. {{ x }}", encoding="utf-8")
    return AgentSpec(
        name="test_agent",
        description="агент для тестов",
        prompt_path=prompt,
        tools=tools,
        max_steps=max_steps,
    )


def make_ctx(variables: dict | None = None, cancellation: CancellationToken | None = None) -> AgentContext:
    return AgentContext(variables={"x": "1"} if variables is None else variables, cancellation=cancellation)


async def collect(runtime: AgentRuntime, spec: AgentSpec, ctx: AgentContext) -> list:
    """Собрать все события запуска агента в список."""
    history = [Message(role="user", content="привет")]
    return [ev async for ev in runtime.run(spec, ctx, history)]


# --- текст без инструментов ---


async def test_text_reply_without_tools(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text="Привет мир"))
    runtime = AgentRuntime(make_router(fake), make_tools())

    events = await collect(runtime, make_spec(tmp_path), make_ctx())

    types = [e.type for e in events]
    assert types[0] == "text"
    assert types[-1] == "final"
    assert "tool_start" not in types and "tool_end" not in types
    # фейковый стрим добавляет пробел после каждого слова
    assert "".join(e.text for e in events if e.type == "text") == "Привет мир "
    assert events[-1].text == "Привет мир "


# --- tool call → карточка → финал ---


async def test_tool_call_flow_with_card(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("echo", text="привет")]),
        FakeTurn(text="Готово"),
    )
    runtime = AgentRuntime(make_router(fake), make_tools())

    events = await collect(runtime, make_spec(tmp_path), make_ctx())

    types = [e.type for e in events]
    # usage приходит в конце каждого стрима LLM, до/после выполнения инструментов
    assert types == ["usage", "tool_start", "card", "tool_end", "text", "usage", "final"]
    tool_start, card, tool_end = events[1], events[2], events[3]
    assert tool_start.name == "echo" and tool_start.label == "Эхо"
    assert tool_start.args == {"text": "привет"}
    assert card.card == {"type": "echo", "text": "привет"}
    assert tool_end.ok is True and tool_end.summary == "ок"
    # usage-события несут расход токенов шага
    assert events[0].usage == (10, 10)


# --- max_steps ---


async def test_max_steps_yields_error(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("echo", text="a")]),
        FakeTurn(tool_calls=[FakeLLMProvider.call("echo", text="b")]),
    )
    runtime = AgentRuntime(make_router(fake), make_tools())

    events = await collect(runtime, make_spec(tmp_path, max_steps=1), make_ctx())

    types = [e.type for e in events]
    assert types[-1] == "error"
    assert "лимит шагов" in events[-1].text
    assert "final" not in types


# --- отмена ---


async def test_cancelled_before_run_yields_error(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text="не успеет"))
    runtime = AgentRuntime(make_router(fake), make_tools())
    token = CancellationToken()
    token.cancel()

    events = await collect(runtime, make_spec(tmp_path), make_ctx(cancellation=token))

    assert [e.type for e in events] == ["error"]
    assert events[0].text == "cancelled"


# --- неизвестный инструмент ---


async def test_unknown_tool_ends_with_ok_false(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("nope", x=1)]),
        FakeTurn(text="Инструмента нет, но я справился"),
    )
    runtime = AgentRuntime(make_router(fake), make_tools())

    events = await collect(runtime, make_spec(tmp_path), make_ctx())

    tool_start = next(e for e in events if e.type == "tool_start")
    tool_end = next(e for e in events if e.type == "tool_end")
    # неизвестному инструменту лейбл = имя, результат — ошибка без исключения
    assert tool_start.label == "nope"
    assert tool_end.ok is False
    assert "недоступен" in tool_end.summary
    # агент продолжает работу и отвечает финалом
    assert events[-1].type == "final"


# --- падение инструмента не роняет агент ---


async def test_tool_exception_becomes_failed_result(tmp_path):
    """Исключение внутри инструмента → tool_end ok=false, агент жив и отвечает финалом."""
    registry = ToolRegistry()

    def boom(args: EchoArgs, ctx: ToolContext) -> dict:
        raise RuntimeError("'BlockDraft' object has no attribute 'model_dump'")

    registry.register(
        ToolSpec(
            name="boom", module="test", description="падает", args_model=EchoArgs, handler=boom, label="Бум"
        )
    )
    fake = FakeLLMProvider()
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("boom", text="x")]),
        FakeTurn(text="Инструмент упал, но я продолжил и ответил"),
    )
    runtime = AgentRuntime(make_router(fake), registry)

    events = await collect(runtime, make_spec(tmp_path, tools=frozenset({"boom"})), make_ctx())

    tool_end = next(e for e in events if e.type == "tool_end")
    assert tool_end.ok is False
    assert "model_dump" in tool_end.summary  # агент видит причину и может сказать о ней
    assert events[-1].type == "final"
    assert "продолжил" in events[-1].text


# --- трейсинг ---


async def test_recorder_captures_ok_run(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("echo", text="привет")]),
        FakeTurn(text="Готово"),
    )
    recorder = ListRecorder()
    runtime = AgentRuntime(make_router(fake), make_tools(), recorder=recorder)

    events = await collect(runtime, make_spec(tmp_path), make_ctx())

    assert [e.type for e in events][-1] == "final"
    assert len(recorder.runs) == 1
    run = recorder.runs[0]
    assert run["status"] == "ok"
    assert run["agent"] == "test_agent"
    assert run["provider"] == "fake"
    assert run["model"] == "fake-model"
    assert run["steps"] == 2
    assert run["tool_calls"] == 1
    assert run["error"] is None


async def test_recorder_captures_cancelled_status(tmp_path):
    fake = FakeLLMProvider()
    recorder = ListRecorder()
    runtime = AgentRuntime(make_router(fake), make_tools(), recorder=recorder)
    token = CancellationToken()
    token.cancel()

    await collect(runtime, make_spec(tmp_path), make_ctx(cancellation=token))

    assert recorder.runs[0]["status"] == "cancelled"
    assert recorder.runs[0]["error"] == "cancelled"


def test_null_recorder_returns_zero():
    assert NullRecorder().record(agent="x", provider="p", model="m", status="ok") == 0


# --- промпт: StrictUndefined ---


def test_render_prompt_strict_undefined(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("Ты тестовый агент. {{ x }}", encoding="utf-8")
    with pytest.raises(UndefinedError):
        render_prompt(prompt, {})


def test_render_prompt_substitutes_variables(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("Ты тестовый агент. {{ x }}", encoding="utf-8")
    assert render_prompt(prompt, {"x": "1"}) == "Ты тестовый агент. 1"


async def test_missing_variable_yields_error_event(tmp_path):
    """Пропущенная переменная промпта не роняет стрим — событие error."""
    fake = FakeLLMProvider()
    runtime = AgentRuntime(make_router(fake), make_tools())

    events = await collect(runtime, make_spec(tmp_path), make_ctx(variables={}))

    assert [e.type for e in events] == ["error"]
    assert "x" in events[0].text


# --- run_structured ---


async def test_run_structured_returns_pydantic_model(tmp_path):
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text='{"answer": "42"}'))
    runtime = AgentRuntime(make_router(fake), make_tools())
    prompt = tmp_path / "structured.md"
    prompt.write_text("Ты отвечаешь JSON. {{ x }}", encoding="utf-8")
    spec = AgentSpec(name="s_agent", description="структурный", prompt_path=prompt, output_model=Out)

    out = await runtime.run_structured(spec, make_ctx(), "вопрос")

    assert isinstance(out, Out) and out.answer == "42"


async def test_run_structured_without_output_model_raises(tmp_path):
    fake = FakeLLMProvider()
    runtime = AgentRuntime(make_router(fake), make_tools())
    spec = make_spec(tmp_path)  # output_model не задан

    with pytest.raises(ValueError, match="output_model"):
        await runtime.run_structured(spec, make_ctx(), "вопрос")
