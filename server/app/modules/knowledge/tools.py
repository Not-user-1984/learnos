"""Инструменты модуля knowledge (MCP + агенты)."""

from pydantic import BaseModel

from ...kernel.tools.spec import ToolContext, ToolSpec
from .schemas import BlockDraftIn


class SaveNoteArgs(BaseModel):
    """save_note: блок-конспект; без draft_json — генерация из разговора."""

    title: str | None = None
    draft_json: BlockDraftIn | None = None
    source: str | None = None
    chapter: int | None = None
    conversation: str | None = None


class ListBlocksArgs(BaseModel):
    """list_blocks с фильтрами."""

    category: str | None = None
    tag: str | None = None
    kind: str | None = None
    source: str | None = None
    q: str | None = None
    sort: str = "created"
    course_id: int | None = None


class GetBlockArgs(BaseModel):
    """get_block по uid."""

    block_uid: str


class UpdateBlockArgs(BaseModel):
    """update_block: patch_json применяется сразу, старая версия сохраняется."""

    block_uid: str
    patch_json: dict
    reason: str = "правка из разговора"


class VersionsArgs(BaseModel):
    """История версий блока."""

    block_uid: str


class RestoreArgs(BaseModel):
    """Откат к версии."""

    block_uid: str
    version: int


class CreateCategoryArgs(BaseModel):
    """create_category: новый узел дерева."""

    path: str
    title: str
    color: str | None = None
    icon: str | None = None


class SetCategoryArgs(BaseModel):
    """set_block_category: агент ставит категорию (confirm=false), пользователь подтверждает в UI."""

    block_uid: str
    path: str | None = None
    confirm: bool = False


class NoArgs(BaseModel):
    """Без аргументов."""


def knowledge_tools(c) -> list[ToolSpec]:
    """Инструменты базы знаний."""
    svc = c.knowledge

    def save_note(args: SaveNoteArgs, ctx: ToolContext):
        draft_in = args.draft_json or _draft_from_conversation(c, ctx, args)
        if draft_in is None:
            return {"error": "validation_failed", "message": "не удалось собрать драфт: передай draft_json"}
        conv = args.conversation or ctx.conversation_uid
        from .schemas import SourceIn

        sources = list(draft_in.sources)
        if args.source and not any(s.source == args.source for s in sources):
            sources.append(SourceIn(source=args.source, chapter=args.chapter))
        draft_in.sources = sources
        block = svc.save_block(draft_in.to_domain(), conversation_uid=conv, category_status="suggested")
        return {
            "ok": True,
            "block_uid": block.meta.uid,
            "kind": block.meta.kind,
            "title": block.meta.title,
            "summary": block.meta.summary,
            "category_suggested": block.meta.category_path,
            "category_status": "suggested",
            "version": 1,
            "_card": {
                "type": "block_saved",
                "block_uid": block.meta.uid,
                "kind": block.meta.kind,
                "title": block.meta.title,
                "summary": block.meta.summary,
                "category_suggested": block.meta.category_path,
                "category_status": "suggested",
                "version": 1,
            },
        }

    def list_blocks(args: ListBlocksArgs, ctx: ToolContext):
        del ctx
        items = svc.list_blocks(
            category=args.category,
            tag=args.tag,
            kind=args.kind,
            source=args.source,
            q=args.q,
            sort=args.sort,
        )
        return [_meta_to_dict(m) for m in items]

    def get_block(args: GetBlockArgs, ctx: ToolContext):
        del ctx
        b = svc.get_block(args.block_uid)
        return {**_meta_to_dict(b.meta), "content": b.content}

    def update_block(args: UpdateBlockArgs, ctx: ToolContext):
        b = svc.update_block(args.block_uid, args.patch_json, args.reason, ctx.conversation_uid)
        return {
            "ok": True,
            "block_uid": b.meta.uid,
            "title": b.meta.title,
            "version": b.meta.version,
            "_card": {
                "type": "block_updated",
                "block_uid": b.meta.uid,
                "title": b.meta.title,
                "from_version": b.meta.version - 1,
                "to_version": b.meta.version,
                "reason": args.reason,
            },
        }

    def list_versions(args: VersionsArgs, ctx: ToolContext):
        del ctx
        return svc.versions(args.block_uid)

    def restore_version(args: RestoreArgs, ctx: ToolContext):
        del ctx
        b = svc.restore_version(args.block_uid, args.version)
        return {"ok": True, "block_uid": b.meta.uid, "version": b.meta.version}

    def list_categories(args: NoArgs, ctx: ToolContext):
        del ctx
        return svc.category_tree()

    def create_category(args: CreateCategoryArgs, ctx: ToolContext):
        del ctx
        cat = svc.create_category(args.path, args.title, args.color, args.icon)
        return {"ok": True, "path": cat.path, "title": cat.title}

    def set_category(args: SetCategoryArgs, ctx: ToolContext):
        del ctx
        b = svc.set_block_category(args.block_uid, args.path, args.confirm)
        return {
            "ok": True,
            "block_uid": b.meta.uid,
            "category": b.meta.category_path,
            "status": b.meta.category_status,
        }

    return [
        ToolSpec(
            name="save_note",
            module="knowledge",
            description="Сохранить блок-конспект (kind: note). Без draft_json — генерация из разговора.",
            args_model=SaveNoteArgs,
            handler=save_note,
            label="Сохраняю конспект",
        ),
        ToolSpec(
            name="list_blocks",
            module="knowledge",
            description="Блоки базы знаний с фильтрами: category, tag, kind, source, q, sort.",
            args_model=ListBlocksArgs,
            handler=list_blocks,
            label="Ищу блоки",
        ),
        ToolSpec(
            name="get_block",
            module="knowledge",
            description="Блок KB целиком (frontmatter + markdown).",
            args_model=GetBlockArgs,
            handler=get_block,
            label="Читаю блок",
        ),
        ToolSpec(
            name="update_block",
            module="knowledge",
            description=(
                "Правка блока: patch_json (поля BlockDraft или "
                "append_theses/append_examples/append_concepts/append_weak_spots), "
                "применяется сразу, версия +1, откат доступен."
            ),
            args_model=UpdateBlockArgs,
            handler=update_block,
            label="Правлю блок",
        ),
        ToolSpec(
            name="list_block_versions",
            module="knowledge",
            description="История версий блока.",
            args_model=VersionsArgs,
            handler=list_versions,
            label="История версий",
        ),
        ToolSpec(
            name="restore_block_version",
            module="knowledge",
            description="Откат блока к версии.",
            args_model=RestoreArgs,
            handler=restore_version,
            label="Откатываю версию",
        ),
        ToolSpec(
            name="list_categories",
            module="knowledge",
            description="Дерево категорий со счётчиками.",
            args_model=NoArgs,
            handler=list_categories,
            label="Категории",
        ),
        ToolSpec(
            name="create_category",
            module="knowledge",
            description="Создать категорию (если ни одна не подходит).",
            args_model=CreateCategoryArgs,
            handler=create_category,
            label="Новая категория",
        ),
        ToolSpec(
            name="set_block_category",
            module="knowledge",
            description=(
                "Поставить блоку категорию; агент — confirm=false, подтверждение — пользователь в UI."
            ),
            args_model=SetCategoryArgs,
            handler=set_category,
            label="Категория блока",
        ),
    ]


def _meta_to_dict(m) -> dict:
    return {
        "block_uid": m.uid,
        "kind": m.kind,
        "title": m.title,
        "summary": m.summary,
        "category_path": m.category_path,
        "category_status": m.category_status,
        "tags": list(m.tags),
        "weak_spots_count": m.weak_spots_count,
        "version": m.version,
        "created_at": m.created,
        "updated_at": m.updated,
    }


def _draft_from_conversation(c, ctx: ToolContext, args: SaveNoteArgs) -> BlockDraftIn | None:
    """Генерация драфта block_writer'ом из истории разговора."""
    from .schemas import BlockDraftIn

    try:
        generated = c.chat.generate_block_draft(
            conversation_uid=ctx.conversation_uid or args.conversation,
            kind="note",
            title_hint=args.title,
        )
    except Exception:  # noqa: BLE001 — без LLM возвращаемся к явному draft_json
        return None
    if generated is None:
        return None
    return BlockDraftIn(**generated.model_dump())
