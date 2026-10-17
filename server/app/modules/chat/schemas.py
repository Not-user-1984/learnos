"""DTO чата."""

from pydantic import BaseModel, Field

MODES = {"free", "quick", "session", "tuning"}


class ConversationCreate(BaseModel):
    """Новый разговор."""

    mode: str = "free"
    activity: str | int | None = None
    chapter: int | None = None
    focus_block: str | None = None
    title: str | None = None


class ConversationPatch(BaseModel):
    """Правка разговора."""

    title: str | None = None


class MessageIn(BaseModel):
    """Сообщение пользователя."""

    content: str = Field(min_length=1)


class MessageOut(BaseModel):
    """Сообщение в ленте."""

    id: int
    role: str
    content: str
    cards: list[dict] = []
    created_at: str


class ConversationItem(BaseModel):
    """Разговор в списке."""

    uid: str
    title: str
    mode: str
    updated_at: str
    messages_count: int = 0
