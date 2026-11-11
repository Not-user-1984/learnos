"""Сервис базы знаний: сохранение, правка, версии, категории, reindex."""

import logging
from typing import Any

from ...kernel.clock import Clock, now_iso
from ...kernel.errors import Conflict, NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
from .domain import (
    Block,
    BlockDraft,
    BlockMeta,
    Category,
    apply_patch,
    normalize_category_path,
    parse_markdown,
)
from .domain import assemble_frontmatter as _assemble  # noqa: F401 — используют usecases
from .domain import dict_of_meta as _dict_of  # noqa: F401
from .domain import writer_out_to_draft as _writer_out_to_draft  # noqa: F401 — тесты/легаси
from .events import BlockDeleted, BlockSaved, BlockUpdated
from .infra.md_store import MdBlockStore
from .infra.sql_repo import BlockRepository, CategoryRepository
from .infra.versions_repo import BlockVersionsRepository
from .usecases.frontmatter import draft_from_frontmatter

log = logging.getLogger("learnos.knowledge")


class KnowledgeService:
    """Use-cases базы знаний. Блок всегда пишется в MD-файл и в индекс в одной операции."""

    def __init__(
        self,
        uow,
        files: MdBlockStore,
        blocks: BlockRepository,
        versions: "BlockVersionsRepository",
        categories: CategoryRepository,
        ids: IdGenerator,
        clock: Clock,
        runtime=None,
        profile=None,
    ) -> None:
        self._uow = uow
        self._files = files
        self._blocks = blocks
        self._versions = versions
        self._cats = categories
        self._ids = ids
        self._clock = clock
        self._runtime = runtime
        self._profile = profile
        self._courses = None  # ставится в bootstrap (проверка ссылки из элемента курса)
        self._generation = None  # ставится в wire модуля (usecases/generation, B-009)

    def bind_generation(self, generation) -> None:
        """Use-cases генерации (B-009)."""
        self._generation = generation

    def bind_categories(self, categories_uc) -> None:
        """Use-cases категорий (B-009)."""
        self._categories_uc = categories_uc

    def bind_blocks_ops(self, blocks_ops) -> None:
        """Use-cases операций над блоками (B-009)."""
        self._blocks_ops = blocks_ops

    def bind_courses(self, courses) -> None:
        """Публичный сервис курсов — для запрета удаления блока из элементов курса."""
        self._courses = courses

    # --- сохранение ---

    def save_block(
        self,
        draft: BlockDraft,
        *,
        session_uid: str | None = None,
        conversation_uid: str | None = None,
        activity_uid: str | None = None,
        category_status: str = "suggested",
        verified: bool = False,
    ) -> Block:
        """Записать новый блок: MD-файл + индекс; категория — предложенная агентом или None."""
        uid = self._ids.new("blk")
        now = now_iso(self._clock)
        category = draft.category_suggestion
        if category:
            category = normalize_category_path(category)
            self._ensure_category(category)
        stem = self._files.write(
            uid,
            draft,
            {
                "session_uid": session_uid,
                "conversation_uid": conversation_uid,
                "activity_uid": activity_uid,
                "created": now,
                "updated": now,
                "version": 1,
                "category_status": category_status,
                "verified": verified,
            },
        )
        meta = BlockMeta(
            uid=uid,
            title=draft.title,
            kind=draft.kind,
            summary=draft.summary,
            category_path=category,
            category_status=category_status,
            tags=draft.tags,
            sources=draft.sources,
            session_uid=session_uid,
            conversation_uid=conversation_uid,
            activity_uid=activity_uid,
            version=1,
            created=now,
            updated=now,
            links=draft.links,
            weak_spots_count=draft.weak_spots_count(),
            path=stem,
            verified=verified,
        )
        with self._uow() as uow:
            self._blocks.save(uow.session, meta, concepts=draft.concepts)
            uow.emit(BlockSaved(block_uid=uid, kind=draft.kind, title=draft.title, category_path=category))
        return Block(meta=meta, content=self._files.read(stem))

    def update_block(self, uid: str, patch: dict, reason: str, conversation_uid: str | None = None) -> Block:
        """Применить правку сразу: старая версия → block_versions, файл и индекс обновляются.

        Raises:
            NotFound: блока с таким uid нет.
        """
        now = now_iso(self._clock)
        with self._uow() as uow:
            block = self._blocks.get(uow.session, uid)
            content = self._files.read(block.meta.path)
            meta_raw, _body = parse_markdown(content)
            draft = self._draft_from_frontmatter(meta_raw, content)
            try:
                new_draft = apply_patch(draft, patch)
            except ValueError as e:
                raise ValidationFailed(str(e)) from e
            self._versions.add_version(
                uow.session, uid, block.meta.version, content, reason, conversation_uid, now
            )
            version = block.meta.version + 1
            stem = self._files.write(
                uid,
                new_draft,
                {
                    "session_uid": block.meta.session_uid,
                    "conversation_uid": block.meta.conversation_uid,
                    "activity_uid": block.meta.activity_uid,
                    "created": block.meta.created,
                    "updated": now,
                    "version": version,
                    # подтверждённая категория, SRS-состояние и «проговорённость»
                    # переживают пересборку файла
                    "category_status": meta_raw.get("category_status", block.meta.category_status),
                    "verified": bool(meta_raw.get("verified", block.meta.verified)),
                    "review": meta_raw.get("review"),
                },
                existing_name=block.meta.path,
            )
            new_meta = BlockMeta(
                **{
                    **_dict_of(block.meta),
                    "title": new_draft.title,
                    "kind": new_draft.kind,
                    "summary": new_draft.summary,
                    "tags": new_draft.tags,
                    "sources": new_draft.sources,
                    "links": new_draft.links,
                    "weak_spots_count": new_draft.weak_spots_count(),
                    "version": version,
                    "updated": now,
                    "path": stem,
                }
            )
            self._blocks.update_row(uow.session, new_meta, concepts=new_draft.concepts)
            uow.emit(BlockUpdated(block_uid=uid, version=version, reason=reason))
            return Block(meta=new_meta, content=self._files.read(stem))

    def restore_version(self, uid: str, version: int, reason: str = "откат") -> Block:
        """Откат к версии (usecases/blocks_ops, B-009)."""
        return self._blocks_ops.restore_version(uid, version, reason)

    # --- чтение ---

    def get_block(self, uid: str) -> Block:
        """Блок целиком: индекс + метаданные связей + MD-тело."""
        with self._uow() as uow:
            block = self._blocks.get(uow.session, uid)
            meta = self._blocks.meta_with_relations(uow.session, block.meta)
            return Block(meta=meta, content=self._files.read(meta.path))

    def list_blocks(self, **filters: Any) -> list[BlockMeta]:
        """Список блоков с фильтрами (см. BlockRepository.list)."""
        with self._uow() as uow:
            return self._blocks.list(uow.session, **filters)

    def titles_map(self, uids: list[str]) -> dict[str, str]:
        """uid → title для рендера связей."""
        with self._uow() as uow:
            out = {}
            for uid in uids:
                try:
                    out[uid] = self._blocks.get(uow.session, uid).meta.title
                except NotFound:
                    out[uid] = uid
            return out

    def inbox(self) -> list[BlockMeta]:
        """Блоки с неподтверждённой категорией."""
        return self.list_blocks(status="inbox")

    def versions(self, uid: str) -> list[dict]:
        """История версий блока."""
        with self._uow() as uow:
            self._blocks.get(uow.session, uid)  # 404, если блока нет
            return self._versions.versions(uow.session, uid)

    def get_version_content(self, uid: str, version: int) -> str:
        """Полный MD-контент версии."""
        with self._uow() as uow:
            return self._versions.get_version(uow.session, uid, version)

    def tags(self) -> dict[str, int]:
        """Теги с числом блоков."""
        with self._uow() as uow:
            return self._blocks.tags_counts(uow.session)

    def count_for_source(self, source_uid: str) -> int:
        """Число блоков по источнику (для запрета удаления источника)."""
        from sqlalchemy import func, select

        from .infra.tables import block_sources as bs

        with self._uow() as uow:
            return int(
                uow.session.execute(select(func.count()).where(bs.c.source_uid == source_uid)).scalar_one()
            )

    def count_for_session(self, session_uid: str) -> int:
        """Число блоков, созданных по сессии (для запрета удаления сессии)."""
        from sqlalchemy import func, select

        from .infra.tables import blocks as blocks_t

        with self._uow() as uow:
            return int(
                uow.session.execute(
                    select(func.count()).where(blocks_t.c.session_uid == session_uid)
                ).scalar_one()
            )

    def block_card_for_session(self, session_uid: str) -> dict | None:
        """Карточка уже сохранённого блока сессии (идемпотентный повтор finish_session).

        Возвращает тот же формат, что и LearningService._write_block, или None.
        """
        with self._uow() as uow:
            meta = self._blocks.get_by_session(uow.session, session_uid)
            if meta is None:
                return None
            return {
                "block_uid": meta.uid,
                "path": meta.path,
                "_card": {
                    "type": "block_saved",
                    "block_uid": meta.uid,
                    "kind": meta.kind,
                    "title": meta.title,
                    "summary": meta.summary,
                    "category": meta.category_path,
                    "category_status": meta.category_status,
                    "version": meta.version,
                },
            }

    def delete_block(self, uid: str) -> dict:
        """Удалить блок: индекс, версии, MD-файл и поисковую строку.

        Запрещено, если блок входит в элементы курса (без каскадов, как с источниками).

        Raises:
            NotFound: блока нет.
            Conflict: на блок ссылаются элементы курса.
        """
        with self._uow() as uow:
            block = self._blocks.get(uow.session, uid)
            if self._courses is not None:
                used = self._courses.count_items_for_block(uid)
                if used:
                    raise Conflict(
                        f"блок «{block.meta.title}» входит в {used} элемент(ов) курса — "
                        "сначала уберите его из курсов"
                    )
            self._blocks.delete(uow.session, uid)
            uow.emit(BlockDeleted(block_uid=uid))
        self._files.delete(block.meta.path)
        return {"ok": True, "deleted": uid}

    # --- категории (перенесено в usecases/categories.py, B-009) ---

    def category_tree(self) -> list[dict]:
        """Дерево категорий со счётчиками."""
        return self._categories_uc.tree()

    def ensure_categories_default(self) -> None:
        """Записать стартовое дерево, если категорий нет."""
        self._categories_uc.ensure_default()

    def create_category(
        self, path: str, title: str, color: str | None = None, icon: str | None = None, sort: int = 0
    ) -> Category:
        """Создать узел дерева."""
        return self._categories_uc.create(path, title, color, icon, sort)

    def update_category(self, path: str, **kwargs: Any) -> Category:
        """Переименовать/перекрасить категорию."""
        return self._categories_uc.update(path, **kwargs)

    def list_categories(self) -> list[Category]:
        """Плоский список категорий."""
        return self._categories_uc.list()

    def set_block_category(self, uid: str, path: str | None, confirm: bool) -> Block:
        """Поставить блоку категорию."""
        return self._categories_uc.set_block_category(uid, path, confirm)

    # --- reindex ---

    def reindex(self) -> dict:
        """Пересобрать индекс знаний из kb/ (usecases/blocks_ops, B-009)."""
        return self._blocks_ops.reindex()

    # --- генерация блока агентами (перенесено в usecases/generation.py, B-009) ---

    def generate_from_dialog(self, dialog: str, kind: str = "note", extra_lines: list[str] | None = None):
        """Драфт блока из переписки разговора (порт для chat, B-009)."""
        return self._generation.generate_from_dialog(dialog, kind=kind, extra_lines=extra_lines)

    def generate_from_transcript(self, session: dict):
        """Собрать BlockDraft из транскрипта сессии."""
        return self._generation.generate_from_transcript(session)

    def categorize_draft(self, draft):
        """Проставить драфту category_suggestion через categorizer."""
        return self._generation.categorize_draft(draft)

    def generate_runbook(self, session: dict, lesson_uid: str):
        """Собрать runbook-драфт из practice_log транскрипта."""
        return self._generation.generate_runbook(session, lesson_uid)

    # --- внутреннее ---

    def _ensure_category(self, path: str) -> None:
        with self._uow() as uow:
            cats = {c.path for c in self._cats.all(uow.session)}
            missing = []
            parts = path.split("/")
            for i in range(1, len(parts) + 1):
                p = "/".join(parts[:i])
                if p not in cats:
                    missing.append(p)
            for p in missing:
                parent = "/".join(p.split("/")[:-1]) or None
                self._cats.ensure(uow.session, Category(path=p, title=p.split("/")[-1], parent_path=parent))
            if missing:
                all_cats = self._cats.all(uow.session)
        if missing:
            self._files.write_categories(all_cats)

    def _draft_from_frontmatter(self, meta_raw: dict, content: str) -> BlockDraft:
        """Парсинг frontmatter+тела в BlockDraft — usecases/frontmatter (B-009)."""
        return draft_from_frontmatter(meta_raw, content)


# чистые функции переехали в domain (B-009); алиасы для старых вызовов
