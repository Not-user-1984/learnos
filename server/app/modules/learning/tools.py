"""Инструменты модуля learning (MCP + агенты)."""

from pydantic import BaseModel

from ...kernel.errors import NotFound
from ...kernel.tools.spec import ToolContext, ToolSpec


class _ListActsArgs(BaseModel):
    """list_activities без обязательных аргументов."""

    status: str | None = None


class StartSessionArgs(BaseModel):
    """start_session: одно из course_id/activity обязательно."""

    course_id: int | None = None
    activity: str | int | None = None
    chapter: int | None = None
    config: dict = {}


class AdvanceArgs(BaseModel):
    """advance: событие стейт-машины + payload."""

    session_id: int | str | None = None
    event: str
    payload: dict = {}


class FinishArgs(BaseModel):
    """finish_session: block_json опционален (без него — генерация из транскрипта)."""

    session_id: int | str | None = None
    block_json: dict | None = None


class PracticeArgs(BaseModel):
    """practice_step: команда для пользователя."""

    session_id: int | str | None = None
    machine: str
    command: str
    explanation: str
    expected: str | None = None
    risk: str = "low"
    verify: str | None = None
    cleanup: str | None = None


class StartActivityArgs(BaseModel):
    """start_activity: «идём по источнику»."""

    source: str | int
    course_id: int | None = None


class RefArgs(BaseModel):
    """Ссылка на активность/сессию."""

    ref: str | int


class StateArgs(BaseModel):
    """Состояние сессии."""

    session_id: int | str


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
            course_id=args.course_id, activity_ref=args.activity, chapter_idx=args.chapter, config=args.config
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
