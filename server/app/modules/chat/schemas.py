"""DTO чата."""

from pydantic import BaseModel, Field

MODES = {"free", "quick", "session", "tuning", "root"}


class ConversationCreate(BaseModel):
    """Новый разговор."""

    mode: str = "root"
    activity: str | int | None = None
    chapter: int | None = None
    focus_block: str | None = None
    title: str | None = None


class ConversationPatch(BaseModel):
    """Правка разговора."""

    title: str | None = None


class MessageAttachment(BaseModel):
    """Вложение сообщения: источник, уже загруженный через /api/sources/upload (PDF)."""

    source_uid: str


class MessageIn(BaseModel):
    """Сообщение пользователя."""

    content: str = Field(min_length=1)
    # режим ресёрча: инструкция уходит агенту в system_extra, в чате видна только тема
    research: bool = False
    attachments: list[MessageAttachment] = Field(default_factory=list, max_length=4)


class ConversationItem(BaseModel):
    """Разговор в списке."""

    uid: str
    title: str
    mode: str
    updated_at: str
    messages_count: int = 0
