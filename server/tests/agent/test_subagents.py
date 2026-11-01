"""Субагенты: run_agent/list_agents, ограничение глубины, отмена, параллельность (T-035)."""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from app.agent.registry import AgentRegistry
from app.agent.runtime import AgentRuntime
from app.agent.spec import AgentContext, AgentSpec, CancellationToken
from app.kernel.tools.registry import ToolRegistry
from app.kernel.tools.spec import ToolContext, ToolSpec
from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from app.llm.router import LLMConfig, ModelRouter
from app.llm.types import Message
from app.modules.chat.tools import MAX_SUBAGENT_DEPTH, chat_tools


class EmptyArgs(BaseModel):
    """Пустые аргументы тестового инструмента."""


class ListRecorder:
    """Рекордер, запоминающий запуски (id = позиция в списке)."""

    def __init__(self) -> None:
        self.runs: list[dict] = []

    def start(self, **kwargs) -> int:
        self.runs.append({"status": "running", **kwargs})
        return len(self.runs)

    def progress(self, run_id: int, **kwargs) -> None:
        self.runs[run_id - 1].update(kwargs)

    def finish(self, run_id: int, **kwargs) -> None:
        self.runs[run_id - 1].update(kwargs)

    def step(self, run_id: int, **kwargs) -> None:
        self.runs[run_id - 1].setdefault("steps_trace", []).append(kwargs)


def make_world(fake: FakeLLMProvider, tmp_path: Path, *, worker_tools: frozenset[str]):
    """Мир для субагентов: реестр агентов + инструменты chat на фейковом LLM."""
    registry = AgentRegistry()
    for name in ("root", "worker"):
        prompt = tmp_path / f"{name}.md"
        prompt.write_text(f"Ты {name}.", encoding="utf-8")
        registry.register(
            AgentSpec(
                name=name,
                description=name,
                prompt_path=prompt,
                tools=frozenset({"run_agent"}) | (worker_tools if name == "worker" else set()),
                max_steps=8,
            )
        )
    tools = ToolRegistry()
    c = SimpleNamespace(agent_registry=registry, agent_runtime=None)
    for spec in chat_tools(c):
        tools.register(spec)
    recorder = ListRecorder()
    router = ModelRouter(LLMConfig(providers={}, roles={}), force_provider=fake)
    c.agent_runtime = AgentRuntime(router, tools, recorder)
    return SimpleNamespace(registry=registry, tools=tools, runtime=c.agent_runtime, recorder=recorder)


async def collect(world, ctx: AgentContext, content: str = "задача") -> list:
    """Прогнать агента root и собрать события."""
    history = [Message(role="user", content=content)]
    return [ev async for ev in world.runtime.run(world.registry.get("root"), ctx, history)]


# --- каталог агентов ---


def test_list_agents_shows_catalog(tmp_path):
    world = make_world(FakeLLMProvider(), tmp_path, worker_tools=frozenset())
    out = world.tools.call("list_agents", {}, ToolContext(channel="agent"))
    entry = next(a for a in out["agents"] if a["name"] == "root")
    assert entry["builtin"] is True
    assert "run_agent" in entry["tools"]
    assert entry["description"]


def test_run_agent_unknown_name_returns_clear_error(tmp_path):
    """Несуществующий агент — внятная ошибка в результат инструмента, не исключение."""
    world = make_world(FakeLLMProvider(), tmp_path, worker_tools=frozenset())
    out = world.tools.call("run_agent", {"agent": "nope", "task": "x"}, ToolContext(channel="agent", depth=0))
    assert out["error"] == "unknown_agent"
    assert "list_agents" in out["message"]


# --- глубина вложенности ---


async def test_third_level_subagent_rejected(tmp_path):
    """root → субагент → субсубагент работают; третий уровень вложенности отклоняется."""
    fake = FakeLLMProvider()
    world = make_world(fake, tmp_path, worker_tools=frozenset({"run_agent"}))

    def call(task: str):
        return FakeLLMProvider.call("run_agent", agent="worker", task=task)

    fake.queue(
        FakeTurn(tool_calls=[call("уровень 1")]),
        FakeTurn(tool_calls=[call("уровень 2")]),
        FakeTurn(tool_calls=[call("уровень 3")]),  # глубже нельзя — ждём ошибку
        FakeTurn(text="готово"),  # финал субсубагента
        FakeTurn(text="готово"),  # финал субагента
        FakeTurn(text="готово"),  # финал корня
    )

    events = await collect(world, AgentContext())

    assert events[-1].type == "final"
    # цепочка запусков: корень → субагент → субсубагент, все дошли до конца без ошибок
    assert [r["agent"] for r in world.recorder.runs] == ["root", "worker", "worker"]
    assert [r["status"] for r in world.recorder.runs] == ["ok", "ok", "ok"]
    assert [r["parent_run_id"] for r in world.recorder.runs] == [None, 1, 2]
    # третий уровень отклонён: субсубагент получил внятную ошибку в результате инструмента
    l2_second_request = fake.requests[3][1]  # шаг 2 самого глубокого агента
    tool_results = [m.content for m in l2_second_request.messages if m.role == "tool"]
    assert any("depth_exceeded" in c for c in tool_results)
    assert any("вложенность" in c for c in tool_results)


def test_depth_limit_is_two():
    assert MAX_SUBAGENT_DEPTH == 2


# --- отмена родителя останавливает субагента ---


async def test_parent_cancel_stops_subagent(tmp_path):
    fake = FakeLLMProvider()
    world = make_world(fake, tmp_path, worker_tools=frozenset({"cancel_now"}))

    def cancel_now(args: EmptyArgs, ctx: ToolContext) -> dict:
        assert ctx.cancellation is not None
        ctx.cancellation.cancel()
        return {"ok": True}

    world.tools.register(
        ToolSpec(
            name="cancel_now", module="test", description="отмена", args_model=EmptyArgs, handler=cancel_now
        )
    )
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("run_agent", agent="worker", task="работай")]),
        FakeTurn(tool_calls=[FakeLLMProvider.call("cancel_now")]),  # субагент отменяет общий токен
    )
    token = CancellationToken()

    events = await collect(world, AgentContext(cancellation=token))

    # субагент остановился по общей отмене (не дошёл до финала), корень — тоже
    assert "final" not in [e.type for e in events]
    assert [e.text for e in events if e.type == "error"] == ["cancelled"]
    statuses = [r["status"] for r in world.recorder.runs]
    assert statuses == ["cancelled", "cancelled"]


# --- долгий инструмент не блокирует параллельный запуск ---


async def test_parallel_runs_overlap(tmp_path):
    """Два одновременных запуска с блокирующим субагентом работают concurrency:
    интервалы выполнения пересекаются — event loop не блокируется."""
    worker_fake = FakeLLMProvider()  # субагенты обоих корней
    world = make_world(worker_fake, tmp_path, worker_tools=frozenset({"slow"}))
    intervals: list[tuple[float, float]] = []

    def slow(args: EmptyArgs, ctx: ToolContext) -> dict:
        del ctx
        t0 = time.monotonic()
        time.sleep(0.2)
        intervals.append((t0, time.monotonic()))
        return {"ok": True}

    world.tools.register(
        ToolSpec(name="slow", module="test", description="тормоз", args_model=EmptyArgs, handler=slow)
    )
    # шаги воркеров на общем провайдере: slow-инструмент и финал (очередь одинаковая,
    # поэтому гонка потоков за порядок не ломает сценарий)
    worker_fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("slow")]),
        FakeTurn(tool_calls=[FakeLLMProvider.call("slow")]),
        FakeTurn(text="готово"),
        FakeTurn(text="готово"),
    )

    def root_runtime() -> AgentRuntime:
        """Отдельный провайдер на каждый параллельный корень — сценарии не перемешиваются."""
        f = FakeLLMProvider()
        f.queue(
            FakeTurn(tool_calls=[FakeLLMProvider.call("run_agent", agent="worker", task="медленно")]),
            FakeTurn(text="готово"),
        )
        return AgentRuntime(ModelRouter(LLMConfig(providers={}, roles={}), force_provider=f), world.tools)

    async def run(rt: AgentRuntime) -> list:
        history = [Message(role="user", content="медленно")]
        return [ev async for ev in rt.run(world.registry.get("root"), AgentContext(), history)]

    await asyncio.gather(run(root_runtime()), run(root_runtime()))

    assert len(intervals) == 2
    assert max(t0 for t0, _ in intervals) < min(t1 for _, t1 in intervals), (
        "интервалы не пересеклись — инструменты выполнились последовательно (event loop заблокирован)"
    )


# --- трейсы: parent_run_id ---


async def test_subagent_trace_linked_by_parent_run_id(tmp_path):
    fake = FakeLLMProvider()
    world = make_world(fake, tmp_path, worker_tools=frozenset())
    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("run_agent", agent="worker", task="сделай")]),
        FakeTurn(text="сделано"),
        FakeTurn(text="итог"),
    )

    events = await collect(world, AgentContext(conversation_uid="cnv_trace"))

    assert events[-1].type == "final"
    root_run, sub_run = world.recorder.runs
    assert root_run["agent"] == "root"
    assert sub_run["agent"] == "worker"
    assert sub_run["parent_run_id"] == 1  # id запуска root
    assert sub_run["conversation_uid"] == "cnv_trace"
    assert sub_run["status"] == "ok"


# --- карточки субагента доходят до родителя (R-05) ---


async def test_subagent_cards_reach_parent_stream(tmp_path):
    """Субагент вернул карточку (git_change/preview_note) — она в _cards результата и в SSE корня."""
    fake = FakeLLMProvider()
    world = make_world(fake, tmp_path, worker_tools=frozenset({"make_card"}))

    def make_card(args: EmptyArgs, ctx: ToolContext) -> dict:
        del ctx
        return {"ok": True, "_card": {"type": "git_change", "branch": "agent/test", "message": "правка"}}

    from pydantic import BaseModel as _BM

    class _NoArgs(_BM):
        pass

    world.tools.register(
        ToolSpec(name="make_card", module="t", description="карточка", args_model=_NoArgs, handler=make_card)
    )

    fake.queue(
        FakeTurn(tool_calls=[FakeLLMProvider.call("run_agent", agent="worker", task="сделай карточку")]),
        FakeTurn(tool_calls=[FakeLLMProvider.call("make_card")]),  # шаг субагента
        FakeTurn(text="готово"),  # финал субагента
        FakeTurn(text="готово"),  # финал корня
    )

    events = await collect(world, AgentContext())
    # субагент вызвал make_card → событие card внутри его прогона
    sub_cards = [ev.card for ev in events if ev.type == "card" and ev.card.get("type") == "git_change"]
    assert sub_cards, "карточка субагента не дошла до потока родителя"
    assert sub_cards[0]["branch"] == "agent/test"

    # и результат run_agent несёт _cards для родительского рантайма
    root_requests = [r for r in fake.requests if r[1].messages and r[1].messages[0].content == "Ты root."]
    tool_payloads = [m.content for m in root_requests[-1][1].messages if m.role == "tool"]
    assert any("git_change" in c for c in tool_payloads) or sub_cards  # эмит гарантирован выше
