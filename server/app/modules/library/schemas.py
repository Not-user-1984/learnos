"""DTO библиотеки."""

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    """Создание источника (web/video); book — через upload."""

    kind: str
    title: str
    url: str | None = None
    local_path: str | None = None
    course_id: int | None = None


class FromUrlCreate(BaseModel):
    """Добавление материала по ссылке (YouTube/PDF/статья)."""

    url: str = Field(min_length=8, max_length=2000)


class FromUrlOut(BaseModel):
    """Результат добавления по ссылке: источник поставлен в обработку."""

    ok: bool
    uid: str
    kind: str
    title: str
    job_id: int | None = None
    processing: bool


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
    last_error: str | None = None


class ChapterCard(BaseModel):
    """Глава в списке глав."""

    idx: int
    title: str
    tokens_est: int | None = None
    summary: str | None = None
    key_points: list[str] = []
    has_exercises: bool = False
    number: int | None = None
    start_page: int | None = None
    end_page: int | None = None


class JobOut(BaseModel):
    """Статус фонового job."""

    id: int
    kind: str
    target: str | None = None
    status: str
    progress: int = 0
    total: int = 0
    message: str | None = None
    error: str | None = None


class OutlineSection(BaseModel):
    """Секция level-2 внутри главы (закладка PDF)."""

    title: str
    page: int


class OutlineOut(BaseModel):
    """Оглавление книги для PDF-ридера: страницы/номера глав и их секции."""

    source: str
    total_pages: int = 0
    pages: dict[str, int] = {}
    numbers: dict[str, int] = {}
    sections: dict[str, list[OutlineSection]] = {}
