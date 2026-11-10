"""Инструменты LLM-слоя: llm_status — роли/модели и состояние цепочки ключей (BB-005)."""

from pydantic import BaseModel, Field

from ..kernel.tools.spec import ToolContext, ToolSpec


class LlmStatusArgs(BaseModel):
    """llm_status: состояние LLM-слоя; reset_cooldown — снять cooldown ключей."""

    reset_cooldown: bool = Field(
        default=False,
        description=(
            "Снять cooldown всех ключей провайдера (переключить ключ при ошибке квоты); "
            "безопасно — просто очищает карту"
        ),
    )


def llm_tools(router) -> list[ToolSpec]:
    """Инструменты LLM-слоя; router — ModelRouter контейнера."""

    def llm_status(args: LlmStatusArgs, ctx: ToolContext):
        del ctx
        reset = router.reset_cooldowns() if args.reset_cooldown else {}
        return {
            **router.detailed_status(),
            **({"cooldown_reset": reset} if reset else {}),
        }

    return [
        ToolSpec(
            name="llm_status",
            module="llm",
            description=(
                "Состояние LLM: роли → модель/провайдер/params, по провайдеру — цепочка ключей "
                "(номер, рабочий/свободен/cooldown N сек). Значения ключей не отдаются. "
                "reset_cooldown=true снимает cooldown всех ключей — зови, когда все ключи "
                "в cooldown после ошибок квоты, и продолжай работу."
            ),
            args_model=LlmStatusArgs,
            handler=llm_status,
            label="Смотрю состояние LLM",
        ),
    ]
