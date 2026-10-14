"""REST профиля."""

from fastapi import APIRouter

from .schemas import Profile


def make_router(svc) -> APIRouter:
    """Роуты профиля; сервис передаётся из контейнера."""
    router = APIRouter(prefix="/settings", tags=["profile"])

    @router.get("/profile", response_model=Profile)
    def get_profile() -> Profile:
        """Профиль пользователя (машины, обучение)."""
        return svc.get()

    @router.put("/profile", response_model=Profile)
    def put_profile(profile: Profile) -> Profile:
        """Сохранить профиль."""
        return svc.update(profile)

    return router
