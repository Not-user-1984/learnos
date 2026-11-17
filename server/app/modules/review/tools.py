"""Инструменты повторений (MCP + агенты)."""

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class QueueArgs(BaseModel):
    """Очередь повторений (B-014: фильтр по источнику — «закрепить книгу»)."""

    source: str | None = Field(default=None, description="uid источника: набор по книге")
    limit: int = Field(default=5, description="Сколько элементов отдать")


class AnswerArgs(BaseModel):
    """Ответ на вопрос повторения."""

    block_uid: str = Field(description="uid блока (blk_…)")
    answer: str = Field(description="Ответ пользователя своими словами")
    question: str | None = Field(default=None, description="Что спрашивали — контекст для экзаменатора")
    card_id: str | None = Field(
        default=None,
        description="id карточки-суть (из get_review_queue, kind=card): SM-2 двигает карточку",
    )


def review_tools(c) -> list[ToolSpec]:
    """Инструменты повторений."""
    svc = c.review

    def get_review_queue(args: QueueArgs, ctx: ToolContext):
        del ctx
        return {"items": svc.queue(args.limit, source=args.source)}

    def answer_review(args: AnswerArgs, ctx: ToolContext):
        del ctx
        return svc.answer(args.block_uid, args.answer, question=args.question, card_id=args.card_id)

    return [
        ToolSpec(
            name="get_review_queue",
            module="review",
            description=(
                "Очередь повторений на день (слабые места + созревшие). Карточки-суть "
                "(kind=card) несут q/a — их можно спрашивать прямо; kind=block — "
                "повторение блока целиком через чат. source — набор по книге."
            ),
            args_model=QueueArgs,
            handler=get_review_queue,
            label="Очередь повторений",
        ),
        ToolSpec(
            name="answer_review",
            module="review",
            description=(
                "Оценить ответ повторения: SM-2 сдвигает срок, слабый ответ — в «Дозакрепить». "
                "Для карточки-суть передай card_id из очереди — срок сдвинется у карточки."
            ),
            args_model=AnswerArgs,
            handler=answer_review,
            label="Оценка повторения",
        ),
    ]
