"""Инструменты повторений (MCP + агенты)."""

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class NoArgs(BaseModel):
    """Без аргументов."""


class AnswerArgs(BaseModel):
    """Ответ на вопрос повторения."""

    block_uid: str = Field(description="uid блока (blk_…)")
    answer: str = Field(description="Ответ пользователя своими словами")
    question: str | None = Field(default=None, description="Что спрашивали — контекст для экзаменатора")


def review_tools(c) -> list[ToolSpec]:
    """Инструменты повторений."""
    svc = c.review

    def get_review_queue(args: NoArgs, ctx: ToolContext):
        del ctx
        return {"items": svc.queue()}

    def answer_review(args: AnswerArgs, ctx: ToolContext):
        del ctx
        return svc.answer(args.block_uid, args.answer, question=args.question)

    return [
        ToolSpec(
            name="get_review_queue",
            module="review",
            description="Очередь повторений на день (слабые места + созревшие).",
            args_model=NoArgs,
            handler=get_review_queue,
            label="Очередь повторений",
        ),
        ToolSpec(
            name="answer_review",
            module="review",
            description="Оценить ответ повторения: SM-2 сдвигает срок, слабый ответ — в «Дозакрепить».",
            args_model=AnswerArgs,
            handler=answer_review,
            label="Оценка повторения",
        ),
    ]
