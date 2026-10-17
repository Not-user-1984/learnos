"""Инструменты модуля knowledge (MCP + агенты)."""

from pydantic import BaseModel

from ...kernel.tools.spec import ToolContext, ToolSpec
from .schemas import BlockDraftIn


class SaveNoteArgs(BaseModel):
    """save_note: блок-конспект; draft_json/preview_id — готовый драфт, иначе генерация из разговора."""

    title: str | None = None
    draft_json: BlockDraftIn | None = None
    preview_id: int | None = None
    source: str | None = None
    chapter: int | None = None
    conversation: str | None = None


class PreviewNoteArgs(BaseModel):
    """preview_note: превью блока-конспекта из разговора, без записи в базу."""

    instructions: str = ""
    kind: str = "note"


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
        conv = args.conversation or ctx.conversation_uid
        if args.draft_json is not None:
            draft_in = args.draft_json
        elif args.preview_id is not None:
            cached = c.chat.get_draft_preview(conv, args.preview_id)
            if cached is None:
                return {"error": "validation_failed", "message": f"превью #{args.preview_id} не найдено"}
            draft_in = BlockDraftIn(**cached)
        else:
            draft_in = _draft_from_conversation(c, ctx, args)
        if draft_in is None:
            return {"error": "validation_failed", "message": "не удалось собрать драфт: передай draft_json"}
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

    def preview_note(args: PreviewNoteArgs, ctx: ToolContext):
        """Превью конспекта из диалога: драфт сохраняется на сервере, запись — save_note(preview_id)."""
        conv = ctx.conversation_uid
        if not conv:
            return {"error": "validation_failed", "message": "preview_note доступен только внутри разговора"}
        try:
            draft = c.chat.generate_block_draft(
                conversation_uid=conv,
                kind=args.kind,
                instructions=args.instructions or None,
            )
        except Exception:  # noqa: BLE001 — агент расскажет, что превью не собралось
            draft = None
        if draft is None:
            return {
                "error": "generation_failed",
                "message": "не удалось собрать превью: диалог пуст или LLM недоступна",
            }
        preview_id = c.chat.store_draft_preview(conv, draft)
        draft_dict = c.chat.get_draft_preview(conv, preview_id)
        card = {"type": "note_draft", "preview_id": preview_id, "draft": draft_dict}
        return {
            "ok": True,
            "preview_id": preview_id,
            "draft": card["draft"],
            "message": (
                f"превью #{preview_id} «{draft.title}»: "
                f"{len(draft.concepts)} понятий, {len(draft.theses)} тезисов"
            ),
            "_card": card,
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
            description=(
                "Сохранить блок-конспект (kind: note). Апрув превью — preview_id из preview_note; "
                "иначе draft_json или генерация из разговора."
            ),
            args_model=SaveNoteArgs,
            handler=save_note,
            label="Сохраняю конспект",
        ),
        ToolSpec(
            name="preview_note",
            module="knowledge",
            description=(
                "Превью блока-конспекта из разговора (без записи): карточка с понятиями/тезисами. "
                "instructions — обязательные правки пользователя. Запись — только save_note(preview_id) "
                "после явного апрува."
            ),
            args_model=PreviewNoteArgs,
            handler=preview_note,
            label="Собираю превью конспекта",
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
