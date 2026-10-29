"""Инструменты модуля chat: оркестрация субагентов (run_agent, list_agents), T-035."""

from typing import Annotated

from pydantic import BaseModel, Field

from ...agent.runtime import AgentRuntime
from ...agent.spec import AgentContext, AgentSpec
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.tools.spec import ToolContext, ToolSpec
from ...llm.types import Message

# вложенность субагентов: корневой агент → субагент → субсубагент; глубже — ошибка
MAX_SUBAGENT_DEPTH = 2


class RunAgentArgs(BaseModel):
    """Аргументы запуска субагента."""

    agent: str = Field(description="Имя агента из list_agents")
    task: str = Field(
        min_length=1, description="Самодостаточная задача: что сделать, над чем, каким должен быть результат"
    )
    context: str | None = Field(
        default=None, description="Доп. сведения субагенту: uid блоков/источников, ссылки, ограничения"
    )


class ListAgentsArgs(BaseModel):
    """Без аргументов."""


class OfferActionArgs(BaseModel):
    """Аргументы предложения-карточки (T-036)."""

    title: str = Field(description="Короткий заголовок предложения")
    description: str | None = Field(
        default=None, description="Что именно произойдёт при согласии пользователя"
    )


class OfferRepliesArgs(BaseModel):
    """Аргументы карточки кнопок-ответов (T-045)."""

    replies: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        min_length=2,
        max_length=4,
        description="Короткие варианты ответа (2–4): клик отправит текст варианта сообщением",
    )


def chat_tools(c) -> list[ToolSpec]:
    """run_agent и list_agents — фундамент корневого агента-оркестратора."""

    def list_agents(args: ListAgentsArgs, ctx: ToolContext) -> dict:
        del args, ctx
        agents = [
            {
                "name": a.name,
                "description": a.description,
                "tools": sorted(a.tools),
                "builtin": c.agent_registry.is_builtin(a.name),
            }
            for a in sorted(c.agent_registry.all(), key=lambda a: a.name)
        ]
        return {"agents": agents}

    def run_agent(args: RunAgentArgs, ctx: ToolContext) -> dict:
        if ctx.depth >= MAX_SUBAGENT_DEPTH:
            return {
                "error": "depth_exceeded",
                "message": f"вложенность субагентов ограничена {MAX_SUBAGENT_DEPTH} уровнями",
            }
        try:
            spec = c.agent_registry.get(args.agent)
        except KeyError:
            return {
                "error": "unknown_agent",
                "message": f"агент '{args.agent}' не найден — каталог в list_agents",
            }
        sub_ctx = AgentContext(
            system_extra=args.context or "",
            conversation_uid=ctx.conversation_uid,
            parent_run_id=ctx.run_id,
            depth=ctx.depth + 1,
            cancellation=ctx.cancellation,
        )
        return run_coro_sync(_collect_subagent(c.agent_runtime, spec, sub_ctx, args.task))

    def offer_action(args: OfferActionArgs, ctx: ToolContext) -> dict:
        """Показать пользователю карточку-предложение; ответ придёт следующим сообщением."""
        del ctx
        return {
            "offered": True,
            "note": "предложение показано карточкой — закончи ответ и дождись реакции пользователя",
            "_card": {
                "type": "action_offer",
                "title": args.title,
                "description": args.description or "",
            },
        }

    def offer_replies(args: OfferRepliesArgs, ctx: ToolContext) -> dict:
        """Приложить к вопросу кнопки-варианты ответа; клик придёт следующим сообщением."""
        del ctx
        return {
            "offered": True,
            "note": "кнопки показаны — закончи ответ вопросом и дождись реакции пользователя",
            "_card": {
                "type": "quick_replies",
                "replies": list(args.replies),
            },
        }

    return [
        ToolSpec(
            name="run_agent",
            module="chat",
            description=(
                "Запустить агента как субагента и дождаться результата. agent — имя из list_agents; "
                "task — самодостаточная постановка (субагент не видит текущий разговор), "
                "context — доп. сведения. Возвращает итоговый текст субагента и агрегаты "
                "(шаги, вызовы инструментов, токены)."
            ),
            args_model=RunAgentArgs,
            handler=run_agent,
            label=lambda a: f"Субагент: {str(a.get('agent', '?'))}",
        ),
        ToolSpec(
            name="list_agents",
            module="chat",
            description="Каталог доступных агентов: имя, описание, инструменты. Вызывай перед run_agent.",
            args_model=ListAgentsArgs,
            handler=list_agents,
            label="Каталог агентов",
        ),
        ToolSpec(
            name="offer_action",
            module="chat",
            description=(
                "Предложить пользователю действие карточкой с кнопками «Да/Нет» — например, "
                "«Добавить видео в Библиотеку?». Вызывай ДО выполнения действия: молчаливые "
                "загрузки запрещены. После вызова закончи ответ и дождись реакции."
            ),
            args_model=OfferActionArgs,
            handler=offer_action,
            label="Предложение",
        ),
        ToolSpec(
            name="offer_replies",
            module="chat",
            description=(
                "Приложить к вопросу кнопки-варианты ответа (2–4 коротких): «Дальше / Подробнее / "
                "Сессия по этой главе». Клик кнопки отправит текст варианта сообщением. Только для "
                "закрытых вопросов с коротким выбором; открытые вопросы и фейнман-проверки — без кнопок. "
                "Вызывай в конце ответа, вопрос задай текстом сообщения."
            ),
            args_model=OfferRepliesArgs,
            handler=offer_replies,
            label="Кнопки-ответы",
        ),
    ]


async def _collect_subagent(runtime: AgentRuntime, spec: AgentSpec, ctx: AgentContext, task: str) -> dict:
    """Прогнать цикл субагента до конца; собрать текст, статус и агрегаты."""
    text_parts: list[str] = []
    steps = tool_calls = input_tokens = output_tokens = 0
    status = "ok"
    async for ev in runtime.run(spec, ctx, [Message(role="user", content=task)]):
        if ev.type == "text":
            text_parts.append(ev.text)
        elif ev.type == "usage":
            steps += 1
            input_tokens += ev.usage[0]
            output_tokens += ev.usage[1]
        elif ev.type == "tool_start":
            tool_calls += 1
        elif ev.type == "error":
            status = "cancelled" if ev.text == "cancelled" else "error"
    text = "".join(text_parts).strip()
    result = {
        "agent": spec.name,
        "status": status,
        "summary": text[:200] or f"статус: {status}",
        "text": text,
        "steps": steps,
        "tool_calls": tool_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "_card": {
            "type": "subagent_result",
            "agent": spec.name,
            "task": task[:200],
            "summary": text[:600],
            "tokens": input_tokens + output_tokens,
        },
    }
    if status != "ok":
        result["error"] = status
    return result
