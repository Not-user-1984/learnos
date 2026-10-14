"""Инструменты модуля profile."""

from pydantic import BaseModel

from ...kernel.tools.spec import ToolSpec


class NoArgs(BaseModel):
    """Пустые аргументы."""


def profile_tools(c) -> list[ToolSpec]:
    """get_profile — машины и предпочтения для практики."""

    def get_profile(args: NoArgs, ctx) -> dict:
        return c.profile.get().model_dump()

    return [
        ToolSpec(
            name="get_profile",
            module="profile",
            description=(
                "Профиль пользователя: машины (id, name, kind, tools, notes) "
                "и предпочтения обучения. Используй для практики под железо."
            ),
            args_model=NoArgs,
            handler=get_profile,
            label="Профиль",
        )
    ]
