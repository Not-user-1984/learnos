"""AgentRuntime: цикл «модель → инструменты → модель», события, отмена, трейсинг."""

import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal, Protocol

import anyio
from jinja2 import Environment, StrictUndefined, TemplateError
from pydantic import BaseModel

from ..kernel.errors import AppError
from ..kernel.tools.registry import ToolRegistry
from ..kernel.tools.spec import ToolContext
from ..llm.router import ModelRouter
from ..llm.structured import structured_output
from ..llm.types import LLMRequest, Message, ToolSchema
from .spec import AgentCancelled, AgentContext, AgentSpec

log = logging.getLogger("learnos.agent")

_jinja = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)


def render_prompt(path: Path, variables: dict[str, Any], override_root: Path | None = None) -> str:
    """Промпт агента с подстановками; битый Jinja-синтаксис не роняет агента (R-14).

    Override: если в data/prompts/ лежит отредактированная копия — читаем её
    (правки из чата применяются сразу и переживают пересборку контейнера).
    override_root — каталог данных из Settings (без чтения os.environ, R-15).
    """
    actual = resolve_prompt_path(path, override_root=override_root)
    return safe_render(actual.read_text(encoding="utf-8"), variables)


def safe_render(text: str, variables: dict[str, Any]) -> str:
    """Jinja-рендер; при ошибке — фолбэк: только известные переменные через replace.

    DevOps-контент промптов полон {{ .Values }}, {{.Names}} (Helm, docker --format):
    StrictUndefined ронял агента на каждом запуске. В фолбэке такой текст живёт
    как есть, известные переменные подставляются точечно.
    """
    try:
        return _jinja.from_string(text).render(**variables)
    except TemplateError:
        log.warning("промпт содержит битый/чужой Jinja-синтаксис — рендер с частичной подстановкой")
        out = text
        for key, value in variables.items():
            for pattern in (f"{{{{ {key} }}}}", f"{{{{{key}}}}}"):
                out = out.replace(pattern, str(value))
        return out


def validate_prompt(text: str) -> str | None:
    """Проверка промпта при сохранении: предупреждение о непарсящемся Jinja.

    Битый синтаксис не блокирует сохранение — рантайм рендерит его безопасным
    фолбэком (safe_render), но автор промпта должен знать, что подстановки
    переменных в таких местах работать не будут.
    """
    from jinja2 import TemplateSyntaxError

    try:
        _jinja.from_string(text).render()
    except TemplateSyntaxError as e:
        return (
            f"в строке {e.lineno} не парсится Jinja ({e.message}) — "
            "этот фрагмент уйдёт агенту без подстановок"
        )
    return None


def resolve_prompt_path(path: Path, override_root: Path | None = None) -> Path:
    """Путь промпта с учётом override из data/prompts/.

    Корень override — из Settings (аргумент); os.environ — фолбэк для вызовов
    вне контейнера (тесты, CLI), чтобы не было двух источников правды (R-15).
    """
    import os

    marker = os.sep + "modules" + os.sep
    if marker in str(path):
        root = override_root or Path(os.environ.get("LEARNOS_DATA_DIR", Path.cwd() / "data"))
        override = root / "prompts" / str(path).split(marker, 1)[1]
        if override.is_file():
            return override
    return path


def _system_prompt(spec: AgentSpec, ctx: AgentContext, override_root: Path | None = None) -> str:
    """Промпт агента (файл или строка кастомного агента) + блок «Контекст», если задан."""
    if spec.prompt_text is not None:
        prompt = safe_render(spec.prompt_text, ctx.variables)
    else:
        prompt = render_prompt(spec.prompt_path, ctx.variables, override_root=override_root)
    if ctx.system_extra:
        prompt = f"{prompt}\n\n# Контекст\n\n{ctx.system_extra}"
    return prompt


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Событие шага агента: text | tool_start | tool_end | card | final | error | usage."""

    type: Literal["text", "tool_start", "tool_end", "card", "final", "error", "usage"]
    text: str = ""
    call_id: str = ""
    name: str = ""
    args: dict[str, Any] | None = None
    label: str = ""
    ok: bool = True
    summary: str = ""
    card: dict[str, Any] | None = None
    usage: tuple[int, int] = (0, 0)


class RunRecorder(Protocol):
    """Порт записи трейсов запусков агентов (реализация — в БД).

    Строка запуска появляется в начале (start) — её id сразу доступен субагентам
    как parent_run_id; агрегаты и статус дописываются в конце (finish).
    """

    def start(
        self,
        *,
        agent: str,
        provider: str,
        model: str,
        conversation_uid: str | None,
        parent_run_id: int | None = None,
    ) -> int:
        """Записать начало запуска в agent_runs и вернуть его id."""
        ...

    def finish(
        self,
        run_id: int,
        *,
        status: str,
        steps: int,
        tool_calls: int,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        error: str | None,
    ) -> None:
        """Дописать агрегаты и итоговый статус запуска."""
        ...

    def progress(self, run_id: int, *, steps: int, tool_calls: int, current: str | None = None) -> None:
        """Живые агрегаты и текущий инструмент по ходу запуска (статус остаётся running)."""
        ...


class NullRecorder:
    """Заглушка трейсинга для тестов."""

    def start(self, **kwargs: Any) -> int:
        return 0

    def finish(self, run_id: int, **kwargs: Any) -> None:
        pass

    def progress(self, run_id: int, **kwargs: Any) -> None:
        pass

    def step(self, run_id: int, **kwargs: Any) -> None:
        pass


class AgentRegistryLike(Protocol):
    """Порт реестра агентов: актуальный spec по имени (для горячей перезагрузки)."""

    def get(self, name: str) -> AgentSpec: ...


class AgentRuntime:
    """Исполняет агента: собирает запрос, стримит ответ, вызывает инструменты, повторяет до финала."""

    def __init__(
        self,
        router: ModelRouter,
        tools: ToolRegistry,
        recorder: RunRecorder | None = None,
        agent_registry: "AgentRegistryLike | None" = None,
        data_dir: Path | None = None,
    ) -> None:
        self._router = router
        self._tools = tools
        self._recorder = recorder or NullRecorder()
        self._data_dir = data_dir  # корень override-промптов из Settings (R-15)
        self._agent_registry = agent_registry  # живой spec: скиллы, сохранённые агентом, видны сразу

    async def run(
        self, spec: AgentSpec, ctx: AgentContext, history: Sequence[Message]
    ) -> AsyncIterator[AgentEvent]:
        """Чат-цикл агента; события отдаются по мере выполнения."""
        provider, model = self._router.resolve(spec.model_role)
        started = time.monotonic()
        steps = tool_calls = input_tokens = output_tokens = 0
        status, error_text = "ok", None
        run_id = self._recorder.start(
            agent=spec.name,
            provider=getattr(provider, "name", "?"),
            model=model,
            conversation_uid=ctx.conversation_uid,
            parent_run_id=ctx.parent_run_id,
        )
        try:
            messages: list[Message] = [
                Message(role="system", content=_system_prompt(spec, ctx, self._data_dir)),
                *history,
            ]

            for _step in range(spec.max_steps):
                if ctx.cancellation:
                    ctx.cancellation.raise_if_cancelled()
                steps += 1
                live = self._live_spec(spec)
                schemas = self._schemas_for(live)
                assistant_text = ""
                calls = []
                async for event in provider.stream(
                    model,
                    LLMRequest(messages=tuple(messages), tools=tuple(schemas), temperature=spec.temperature),
                ):
                    if event.type == "text" and event.text:
                        assistant_text += event.text
                        yield AgentEvent(type="text", text=event.text)
                    elif event.type == "tool_call" and event.tool_call:
                        calls.append(event.tool_call)
                    elif event.type == "usage" and event.usage:
                        input_tokens += event.usage.input_tokens
                        output_tokens += event.usage.output_tokens
                        self._recorder.step(
                            run_id,
                            idx=steps,
                            kind="llm",
                            name="chat",
                            tokens_in=event.usage.input_tokens,
                            tokens_out=event.usage.output_tokens,
                        )
                        yield AgentEvent(
                            type="usage", usage=(event.usage.input_tokens, event.usage.output_tokens)
                        )

                if not calls:
                    yield AgentEvent(type="final", text=assistant_text)
                    break

                messages.append(Message(role="assistant", content=assistant_text, tool_calls=tuple(calls)))
                for call in calls:
                    tool_calls += 1
                    known = call.name in self._names(live)
                    base_label = self._tools.get(call.name).label if known else call.name
                    label = base_label(call.arguments) if callable(base_label) else base_label
                    # живые агрегаты и текущий инструмент: бейдж «агент работает ·
                    # шаг N · что делает» читает их из agent_runs
                    self._recorder.progress(run_id, steps=steps, tool_calls=tool_calls, current=label)
                    yield AgentEvent(
                        type="tool_start", call_id=call.id, name=call.name, args=call.arguments, label=label
                    )
                    tool_t0 = time.monotonic()
                    if known:
                        try:
                            # офлоад: инструмент синхронный, долгий (сеть, субагент)
                            # не должен блокировать event loop сервера
                            call_ctx = self._tool_ctx(spec, ctx, run_id)
                            result = await anyio.to_thread.run_sync(
                                partial(self._tools.call, call.name, call.arguments, call_ctx)
                            )
                        except Exception as e:  # noqa: BLE001 — падение инструмента не должно ронять агент
                            log.warning("tool %s failed: %s", call.name, e)
                            result = {"error": "tool_failed", "message": f"{call.name}: {e}"[:300]}
                    else:
                        result = {
                            "error": "unknown_tool",
                            "message": f"инструмент '{call.name}' недоступен этому агенту",
                        }
                    tool_ms = int((time.monotonic() - tool_t0) * 1000)
                    for card in ([result.get("_card")] if result.get("_card") is not None else []) + list(
                        result.get("_cards") or []
                    ):
                        yield AgentEvent(type="card", card=card, call_id=call.id, name=call.name)
                    ok = "error" not in result
                    summary = (
                        result.get("message")
                        or result.get("summary")
                        or result.get("title")
                        or ("ок" if ok else "ошибка")
                    )
                    self._recorder.step(
                        run_id,
                        idx=steps,
                        kind="tool",
                        name=call.name,
                        args_json=json.dumps(call.arguments, ensure_ascii=False, default=str)[:2000],
                        result_summary=str(summary)[:200],
                        ok=ok,
                        ms=tool_ms,
                    )
                    yield AgentEvent(
                        type="tool_end", call_id=call.id, name=call.name, ok=ok, summary=str(summary)[:200]
                    )
                    payload = {k: v for k, v in result.items() if k not in ("_card", "_cards")}
                    messages.append(
                        Message(
                            role="tool",
                            content=json.dumps(payload, ensure_ascii=False),
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
            else:
                status = "max_steps"
                yield AgentEvent(type="error", text="Превышен лимит шагов агента")
        except AgentCancelled:
            status, error_text = "cancelled", "cancelled"
            yield AgentEvent(type="error", text="cancelled")
        except AppError as e:
            status, error_text = "error", e.message
            yield AgentEvent(type="error", text=e.message)
        except Exception as e:  # noqa: BLE001 — граница цикла агента
            status, error_text = "error", str(e)
            log.exception("agent %s failed", spec.name)
            yield AgentEvent(type="error", text=str(e))
        finally:
            self._recorder.finish(
                run_id,
                status=status,
                steps=steps,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error_text,
            )

    @staticmethod
    def _tool_ctx(spec: AgentSpec, ctx: AgentContext, run_id: int) -> ToolContext:
        """Контекст вызова инструмента: run_id/depth/cancellation — для оркестрации субагентов."""
        return ToolContext(
            channel="agent",
            conversation_uid=ctx.conversation_uid,
            session_uid=ctx.session_uid,
            agent_name=spec.name,
            run_id=run_id,
            depth=ctx.depth,
            cancellation=ctx.cancellation,
        )

    def _live_spec(self, spec: AgentSpec) -> AgentSpec:
        """Актуальный spec агента: реестр мог расширить инструменты (save_skill в этом же запуске)."""
        if self._agent_registry is None:
            return spec
        try:
            return self._agent_registry.get(spec.name)
        except KeyError:
            return spec  # агента сняли из реестра во время запуска — работаем по снятой копии

    def _names(self, spec: AgentSpec) -> set[str]:
        return set(spec.tools)

    def _schemas_for(self, spec: AgentSpec) -> list[ToolSchema]:
        tools = self._tools.filter(names=set(spec.tools), channel="agent")
        return [ToolSchema(name=t.name, description=t.description, parameters=t.json_schema()) for t in tools]

    async def run_structured(self, spec: AgentSpec, ctx: AgentContext, user_prompt: str) -> BaseModel:
        """Запуск агента как функции: без чата, выход — pydantic-модель output_model."""
        if spec.output_model is None:
            raise ValueError(f"агент '{spec.name}' не объявил output_model")
        provider, model = self._router.resolve(spec.model_role)
        started = time.monotonic()
        status, error_text = "ok", None
        run_id = self._recorder.start(
            agent=spec.name,
            provider=getattr(provider, "name", "?"),
            model=model,
            conversation_uid=ctx.conversation_uid,
            parent_run_id=ctx.parent_run_id,
        )
        tokens = (0, 0)
        try:
            out, tokens = await structured_output(
                provider,
                model,
                [
                    Message(role="system", content=_system_prompt(spec, ctx, self._data_dir)),
                    Message(role="user", content=user_prompt),
                ],
                spec.output_model,
                temperature=spec.temperature,
            )
            self._recorder.step(
                run_id,
                idx=1,
                kind="structured",
                name=spec.output_model.__name__,
                tokens_in=tokens[0],
                tokens_out=tokens[1],
            )
            return out
        except Exception as e:  # noqa: BLE001
            status, error_text = "error", str(e)
            raise
        finally:
            self._recorder.finish(
                run_id,
                status=status,
                steps=1,
                tool_calls=0,
                input_tokens=tokens[0],
                output_tokens=tokens[1],
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error_text,
            )
