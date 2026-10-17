"""AgentRuntime: цикл «модель → инструменты → модель», события, отмена, трейсинг."""

import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from jinja2 import Environment, StrictUndefined
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


def render_prompt(path: Path, variables: dict[str, Any]) -> str:
    """Промпт агента с Jinja-подстановками; StrictUndefined ловит опечатки.

    Override: если в data/prompts/ лежит отредактированная копия — читаем её
    (правки из чата применяются сразу и переживают пересборку контейнера).
    """
    actual = resolve_prompt_path(path)
    return _jinja.from_string(actual.read_text(encoding="utf-8")).render(**variables)


def resolve_prompt_path(path: Path) -> Path:
    """Путь промпта с учётом override из data/prompts/ (если задан LEARNOS_DATA_DIR)."""
    import os

    marker = os.sep + "modules" + os.sep
    if marker in str(path):
        override_root = Path(os.environ.get("LEARNOS_DATA_DIR", Path.cwd() / "data")) / "prompts"
        override = override_root / str(path).split(marker, 1)[1]
        if override.is_file():
            return override
    return path


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
    """Порт записи трейсов запусков агентов (реализация — в БД)."""

    def record(
        self,
        *,
        agent: str,
        provider: str,
        model: str,
        conversation_uid: str | None,
        status: str,
        steps: int,
        tool_calls: int,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        error: str | None,
        parent_run_id: int | None = None,
    ) -> int:
        """Записать один запуск в agent_runs и вернуть его id."""
        ...


class NullRecorder:
    """Заглушка трейсинга для тестов."""

    def record(self, **kwargs: Any) -> int:
        return 0


class AgentRuntime:
    """Исполняет агента: собирает запрос, стримит ответ, вызывает инструменты, повторяет до финала."""

    def __init__(self, router: ModelRouter, tools: ToolRegistry, recorder: RunRecorder | None = None) -> None:
        self._router = router
        self._tools = tools
        self._recorder = recorder or NullRecorder()

    async def run(
        self, spec: AgentSpec, ctx: AgentContext, history: Sequence[Message]
    ) -> AsyncIterator[AgentEvent]:
        """Чат-цикл агента; события отдаются по мере выполнения."""
        provider, model = self._router.resolve(spec.model_role)
        started = time.monotonic()
        steps = tool_calls = input_tokens = output_tokens = 0
        status, error_text = "ok", None
        try:
            system_prompt = render_prompt(spec.prompt_path, ctx.variables)
            if ctx.system_extra:
                system_prompt = f"{system_prompt}\n\n# Контекст\n\n{ctx.system_extra}"
            messages: list[Message] = [Message(role="system", content=system_prompt), *history]
            schemas = self._schemas_for(spec)

            for _step in range(spec.max_steps):
                if ctx.cancellation:
                    ctx.cancellation.raise_if_cancelled()
                steps += 1
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
                        yield AgentEvent(
                            type="usage", usage=(event.usage.input_tokens, event.usage.output_tokens)
                        )

                if not calls:
                    yield AgentEvent(type="final", text=assistant_text)
                    break

                messages.append(Message(role="assistant", content=assistant_text, tool_calls=tuple(calls)))
                for call in calls:
                    tool_calls += 1
                    known = call.name in self._names(spec)
                    base_label = self._tools.get(call.name).label if known else call.name
                    label = base_label(call.arguments) if callable(base_label) else base_label
                    yield AgentEvent(
                        type="tool_start", call_id=call.id, name=call.name, args=call.arguments, label=label
                    )
                    if known:
                        result = self._tools.call(
                            call.name,
                            call.arguments,
                            ToolContext(
                                channel="agent",
                                conversation_uid=ctx.conversation_uid,
                                session_uid=ctx.session_uid,
                                agent_name=spec.name,
                            ),
                        )
                    else:
                        result = {
                            "error": "unknown_tool",
                            "message": f"инструмент '{call.name}' недоступен этому агенту",
                        }
                    card = result.get("_card")
                    if card is not None:
                        yield AgentEvent(type="card", card=card, call_id=call.id, name=call.name)
                    ok = "error" not in result
                    summary = (
                        result.get("message")
                        or result.get("summary")
                        or result.get("title")
                        or ("ок" if ok else "ошибка")
                    )
                    yield AgentEvent(
                        type="tool_end", call_id=call.id, name=call.name, ok=ok, summary=str(summary)[:200]
                    )
                    payload = {k: v for k, v in result.items() if k != "_card"}
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
            self._recorder.record(
                agent=spec.name,
                provider=getattr(provider, "name", "?"),
                model=model,
                conversation_uid=ctx.conversation_uid,
                status=status,
                steps=steps,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error_text,
                parent_run_id=ctx.parent_run_id,
            )

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
        try:
            system_prompt = render_prompt(spec.prompt_path, ctx.variables)
            if ctx.system_extra:
                system_prompt = f"{system_prompt}\n\n# Контекст\n\n{ctx.system_extra}"
            return await structured_output(
                provider,
                model,
                [Message(role="system", content=system_prompt), Message(role="user", content=user_prompt)],
                spec.output_model,
                temperature=spec.temperature,
            )
        except Exception as e:  # noqa: BLE001
            status, error_text = "error", str(e)
            raise
        finally:
            self._recorder.record(
                agent=spec.name,
                provider=getattr(provider, "name", "?"),
                model=model,
                conversation_uid=ctx.conversation_uid,
                status=status,
                steps=1,
                tool_calls=0,
                input_tokens=0,
                output_tokens=0,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error_text,
                parent_run_id=ctx.parent_run_id,
            )
