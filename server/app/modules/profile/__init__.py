"""Модуль «Профиль»: машины пользователя и предпочтения обучения."""

from ...kernel.module import Module


class ProfileModule(Module):
    """Профиль хранится в settings.profile; дефолт задаёт миграция."""

    name = "profile"

    def wire(self, c) -> None:
        from .service import ProfileService

        c.profile = ProfileService(c.uow)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.profile)]

    def tools(self, c):
        from .tools import profile_tools

        return profile_tools(c)
