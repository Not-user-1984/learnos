"""Инструменты модуля learning (MCP + агенты)."""

from pydantic import BaseModel, Field

from ...kernel.errors import NotFound
from ...kernel.tools.spec import ToolContext, ToolSpec


class _ListActsArgs(BaseModel):
    """list_activities без обязательных аргументов."""

    status: str | None = Field(default=None, description="Фильтр по статусу активности")


class StartSessionArgs(BaseModel):
    """start_session: одно из course_id/activity обязательно."""

    course_id: int | None = Field(default=None, description="id курса (сессия в его рамках)")
    activity: str | int | None = Field(default=None, description="uid/id активности источника")
    chapter: int | None = Field(default=None, description="Номер главы (по умолчанию курсор активности)")
    # элемент доски курса, который закроет сессия (B-004): приходит из контекста курса
    course_item_id: int | None = Field(default=None, description="id элемента курса, который закроет сессия")
    config: dict = Field(default_factory=dict, description="Конфиг сессии (concepts, minutes, …)")


class AdvanceArgs(BaseModel):
    """advance: событие стейт-машины + payload."""

    session_id: int | str | None = Field(
        default=None, description="uid/id сессии (из контекста — можно опустить)"
    )
    event: str = Field(description="Событие: theory_done, ask, answer, go_practice, practice_done, note…")
    payload: dict = Field(default_factory=dict, description="Данные события (вопрос/ответ/заметка)")


class FinishArgs(BaseModel):
    """finish_session: block_json опционален (без него — генерация из транскрипта)."""

    session_id: int | str | None = Field(
        default=None, description="uid/id сессии (из контекста — можно опустить)"
    )
    block_json: dict | None = Field(default=None, description="Явный драфт блока-урока (BlockDraft)")


class PracticeArgs(BaseModel):
    """practice_step: команда для пользователя."""

    session_id: int | str | None = Field(
        default=None, description="uid/id сессии (из контекста — можно опустить)"
    )
    machine: str = Field(description="id машины из профиля пользователя")
    command: str = Field(description="Команда для выполнения")
    explanation: str = Field(description="Что делает команда (части через «;» и «—»)")
    expected: str | None = Field(default=None, description="Ожидаемый вывод")
    risk: str = Field(default="low", description="Риск: low | medium | high")


class StartActivityArgs(BaseModel):
    """start_activity: «идём по источнику»."""

    source: str | int = Field(description="uid/id источника")
    course_id: int | None = Field(default=None, description="id курса (курсор в рамках курса)")


class MarkChapterDoneArgs(BaseModel):
    """mark_chapter_done: главу разобрали — двигаем курсор активности."""

    chapter: int | None = Field(default=None, description="Номер главы (по умолчанию текущий курсор)")
    activity: str | int | None = Field(
        default=None, description="uid/id активности (по умолчанию из разговора)"
    )


class RefArgs(BaseModel):
    """Ссылка на активность/сессию."""

    ref: str | int = Field(description="uid или числовой id")


class StateArgs(BaseModel):
    """Состояние сессии."""

    session_id: int | str = Field(description="uid/id сессии")


def learning_tools(c) -> list[ToolSpec]:
    """Инструменты обучения."""
    svc = c.learning

    def _session_ref(args_id, ctx: ToolContext):
        """session_id из аргументов или контекста агента."""
        if args_id is not None:
            return args_id
        if ctx.session_uid:
            return ctx.session_uid
        raise NotFound("session_id не задан (и не из контекста разговора)")

    def start_session(args: StartSessionArgs, ctx: ToolContext):
        del ctx
        return svc.start_session(
            course_id=args.course_id,
            activity_ref=args.activity,
            chapter_idx=args.chapter,
            course_item_id=args.course_item_id,
            config=args.config,
        )

    def get_state(args: StateArgs, ctx: ToolContext):
        del ctx
        out = svc.get_session_state(args.session_id)
        out.pop("_card", None)
        return out

    def advance(args: AdvanceArgs, ctx: ToolContext):
        out = svc.advance(_session_ref(args.session_id, ctx), args.event, args.payload)
        card = out.pop("_card", None)
        result = {k: v for k, v in out.items()}
        if card:
            result["_card"] = card
        return result

    def finish_session(args: FinishArgs, ctx: ToolContext):
        out = svc.finish_session(_session_ref(args.session_id, ctx), args.block_json)
        card = out.pop("_card", None)
        if card:
            out["_card"] = card
        return out

    def practice_step(args: PracticeArgs, ctx: ToolContext):
        return svc.practice_step(
            _session_ref(args.session_id, ctx),
            args.machine,
            args.command,
            args.explanation,
            args.expected,
            args.risk,
        )

    def start_activity(args: StartActivityArgs, ctx: ToolContext):
        del ctx
        return svc.start_activity(args.source, args.course_id)

    def mark_chapter_done(args: MarkChapterDoneArgs, ctx: ToolContext):
        return svc.mark_chapter_done(
            activity_ref=args.activity, chapter=args.chapter, conversation_uid=ctx.conversation_uid
        )

    def list_activities(args: RefArgs | None, ctx: ToolContext):
        del ctx, args
        return svc.list_activities()

    def get_activity(args: RefArgs, ctx: ToolContext):
        del ctx
        return svc.get_activity(args.ref)

    return [
        ToolSpec(
            name="start_session",
            module="learning",
            description=(
                "Начать сессию обучения (нужен course_id или activity). Возвращает состояние стейт-машины."
            ),
            args_model=StartSessionArgs,
            handler=start_session,
            label="Начинаю сессию",
        ),
        ToolSpec(
            name="get_session_state",
            module="learning",
            description="Текущее состояние сессии: state, transcript, allowed_events.",
            args_model=StateArgs,
            handler=get_state,
            label="Состояние сессии",
        ),
        ToolSpec(
            name="advance",
            module="learning",
            description=(
                "Продвинуть сессию. Переходы: theory_done, next_block, go_practice, practice_done; "
                "лог: ask, answer, note, practice_log."
            ),
            args_model=AdvanceArgs,
            handler=advance,
            label="Продвигаю сессию",
        ),
        ToolSpec(
            name="finish_session",
            module="learning",
            description=(
                "Завершить сессию (только из state=debrief) и сохранить блок в KB. block_json опционален."
            ),
            args_model=FinishArgs,
            handler=finish_session,
            label="Завершаю сессию",
        ),
        ToolSpec(
            name="practice_step",
            module="learning",
            description=(
                "Шаг практики: команда под машину из профиля + объяснение. Пользователь выполняет сам."
            ),
            args_model=PracticeArgs,
            handler=practice_step,
            label="Практика",
        ),
        ToolSpec(
            name="start_activity",
            module="learning",
            description="Начать прохождение источника по главам.",
            args_model=StartActivityArgs,
            handler=start_activity,
            label="Начинаю активность",
        ),
        ToolSpec(
            name="mark_chapter_done",
            module="learning",
            description=(
                "Отметить главу источника разобранной: двигает курсор активности "
                "(текущая глава разговора, если chapter не задан). Для быстрого разбора — "
                "вызывай после разбора главы, вместе с предложением следующей."
            ),
            args_model=MarkChapterDoneArgs,
            handler=mark_chapter_done,
            label="Глава пройдена",
        ),
        ToolSpec(
            name="list_activities",
            module="learning",
            description="Активности с прогрессом.",
            args_model=_ListActsArgs,
            handler=list_activities,
            label="Активности",
        ),
        ToolSpec(
            name="get_activity",
            module="learning",
            description="Активность: курсор, главы, блоки.",
            args_model=RefArgs,
            handler=get_activity,
            label="Активность",
        ),
    ]
