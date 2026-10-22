"""DTO библиотеки."""

from pydantic import BaseModel


class SourceCreate(BaseModel):
    """Создание источника (web/video); book — через upload."""

    kind: str
    title: str
    url: str | None = None
    local_path: str | None = None
    course_id: int | None = None


class SourceCard(BaseModel):
    """Карточка источника в списке."""

    id: int
    uid: str
    kind: str
    title: str
    author: str | None = None
    url: str | None = None
    status: str
    summary: str | None = None
    chapters_count: int = 0
    meta: dict = {}


class ChapterCard(BaseModel):
    """Глава в списке глав."""

    idx: int
    title: str
    tokens_est: int | None = None
    summary: str | None = None
    key_points: list[str] = []
    has_exercises: bool = False


class JobOut(BaseModel):
    """Статус фонового job."""

    id: int
    kind: str
    target: str | None
    status: str
    progress: int = 0
    total: int = 0
    message: str | None = None
    error: str | None = None


class OutlineOut(BaseModel):
    """Закладки PDF → стартовая страница каждой главы (для режима «чистый PDF»)."""

    source: str
    total_pages: int = 0
    pages: dict[str, int] = {}
