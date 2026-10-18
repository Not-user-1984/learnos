"""Превью конспекта: кэш драфтов по preview_id + инструменты preview_note / save_note(preview_id)."""

from types import SimpleNamespace

from app.kernel.tools.spec import ToolContext
from app.modules.chat.service import ChatService, _draft_to_plain
from app.modules.knowledge.domain import BlockDraft, Concept
from app.modules.knowledge.tools import PreviewNoteArgs, SaveNoteArgs, knowledge_tools


def make_draft(title: str = "Логирование в Python") -> BlockDraft:
    return BlockDraft(
        title=title,
        summary="конспект по главе",
        kind="note",
        concepts=(Concept("logger", "точка входа для сообщений"),),
        theses=("handler доставляет запись",),
        weak_spots=("уровни vs verbosity",),
        tags=("python", "logging"),
        category_suggestion="Разработка/Python",
    )


def make_chat_service() -> ChatService:
    svc = ChatService.__new__(ChatService)
    svc._previews = {}
    return svc


class FakeChat:
    def __init__(self, draft: BlockDraft | None) -> None:
        self.draft = draft
        self.previews: dict[str, list[dict]] = {}
        self.instructions_seen: str | None = None

    def generate_block_draft(self, conversation_uid, kind, title_hint=None, instructions=None):
        self.instructions_seen = instructions
        return self.draft

    def store_draft_preview(self, conversation_uid: str, draft) -> int:
        self.previews.setdefault(conversation_uid, []).append(_draft_to_plain(draft))
        return len(self.previews[conversation_uid])

    def get_draft_preview(self, conversation_uid, preview_id):
        history = self.previews.get(conversation_uid) or []
        return history[preview_id - 1] if 0 < preview_id <= len(history) else None


class FakeKnowledge:
    def __init__(self) -> None:
        self.saved: list = []
        self.categorized: list = []

    def categorize_draft(self, draft):
        self.categorized.append(draft)
        return draft

    def save_block(self, draft, conversation_uid=None, category_status="suggested"):
        self.saved.append(draft)
        self.category_status = category_status
        meta = SimpleNamespace(
            uid="blk_test01",
            kind=draft.kind,
            title=draft.title,
            summary=draft.summary,
            category_path="Разработка/Python",
        )
        return SimpleNamespace(meta=meta)


def test_draft_to_plain_roundtrip_fields():
    plain = _draft_to_plain(make_draft())
    assert plain["title"] == "Логирование в Python"
    assert plain["concepts"] == [{"term": "logger", "definition": "точка входа для сообщений"}]
    assert plain["tags"] == ["python", "logging"]


def test_preview_cache_store_and_get():
    svc = make_chat_service()
    first = svc.store_draft_preview("cnv_a", make_draft("Один"))
    second = svc.store_draft_preview("cnv_a", make_draft("Два"))
    assert (first, second) == (1, 2)
    assert svc.get_draft_preview("cnv_a", 1)["title"] == "Один"
    assert svc.get_draft_preview("cnv_a", 2)["title"] == "Два"
    assert svc.get_draft_preview("cnv_a", 3) is None
    assert svc.get_draft_preview("cnv_b", 1) is None
    assert svc.get_draft_preview(None, 1) is None


def test_preview_note_returns_card_and_caches():
    chat = FakeChat(make_draft())
    c = SimpleNamespace(chat=chat, knowledge=FakeKnowledge())
    tools = {t.name: t for t in knowledge_tools(c)}
    out = tools["preview_note"].handler(
        PreviewNoteArgs(instructions="убери тезис про handlers"), ToolContext(conversation_uid="cnv_a")
    )
    assert out["ok"] and out["preview_id"] == 1
    assert out["_card"]["type"] == "note_draft"
    assert out["_card"]["draft"]["title"] == "Логирование в Python"
    assert chat.instructions_seen == "убери тезис про handlers"


def test_preview_note_requires_conversation():
    chat = FakeChat(make_draft())
    c = SimpleNamespace(chat=chat, knowledge=FakeKnowledge())
    tools = {t.name: t for t in knowledge_tools(c)}
    out = tools["preview_note"].handler(PreviewNoteArgs(), ToolContext())
    assert "error" in out


def test_save_note_by_preview_id_saves_cached_draft():
    chat = FakeChat(make_draft())
    kb = FakeKnowledge()
    c = SimpleNamespace(chat=chat, knowledge=kb)
    tools = {t.name: t for t in knowledge_tools(c)}
    tools["preview_note"].handler(PreviewNoteArgs(), ToolContext(conversation_uid="cnv_a"))

    out = tools["save_note"].handler(
        SaveNoteArgs(preview_id=1, source="src_x", chapter=2), ToolContext(conversation_uid="cnv_a")
    )
    assert out["ok"] and out["block_uid"] == "blk_test01"
    assert out["_card"]["type"] == "block_saved"
    assert len(kb.saved) == 1
    assert kb.saved[0].sources[0].source == "src_x"
    assert kb.saved[0].sources[0].chapter == 2


def test_save_note_unknown_preview_id_fails_cleanly():
    chat = FakeChat(make_draft())
    kb = FakeKnowledge()
    c = SimpleNamespace(chat=chat, knowledge=kb)
    tools = {t.name: t for t in knowledge_tools(c)}
    out = tools["save_note"].handler(SaveNoteArgs(preview_id=99), ToolContext(conversation_uid="cnv_a"))
    assert out["error"] == "validation_failed"
    assert kb.saved == []
