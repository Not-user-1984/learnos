"""Сервис базы знаний: сохранение, правка, версии, категории, reindex."""

import json
import logging
from typing import Any

from ...agent.spec import AgentContext
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import Clock, now_iso
from ...kernel.errors import NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
from ..library.domain import SourceKind  # noqa: F401 — реэкспорт для удобства слоёв выше
from .domain import (
    Block,
    BlockDraft,
    BlockMeta,
    Category,
    apply_patch,
    default_categories,
    normalize_category_path,
    parse_markdown,
)
from .events import BlockSaved, BlockUpdated, CategoryConfirmed
from .infra.md_store import MdBlockStore
from .infra.sql_repo import BlockRepository, CategoryRepository

log = logging.getLogger("learnos.knowledge")


class KnowledgeService:
    """Use-cases базы знаний. Блок всегда пишется в MD-файл и в индекс в одной операции."""

    def __init__(
        self,
        uow,
        files: MdBlockStore,
        blocks: BlockRepository,
        categories: CategoryRepository,
        ids: IdGenerator,
        clock: Clock,
        runtime=None,
        profile=None,
    ) -> None:
        self._uow = uow
        self._files = files
        self._blocks = blocks
        self._cats = categories
        self._ids = ids
        self._clock = clock
        self._runtime = runtime
        self._profile = profile

    # --- сохранение ---

    def save_block(
        self,
        draft: BlockDraft,
        *,
        session_uid: str | None = None,
        conversation_uid: str | None = None,
        activity_uid: str | None = None,
        category_status: str = "suggested",
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
        )
        with self._uow() as uow:
            self._blocks.save(uow.session, meta)
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
            self._blocks.add_version(
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
            self._blocks.update_row(uow.session, new_meta)
            uow.emit(BlockUpdated(block_uid=uid, version=version, reason=reason))
            return Block(meta=new_meta, content=self._files.read(stem))

    def restore_version(self, uid: str, version: int, reason: str = "откат") -> Block:
        """Откат к версии: текущий контент сохраняется как версия, файл перезаписывается старым."""
        now = now_iso(self._clock)
        with self._uow() as uow:
            block = self._blocks.get(uow.session, uid)
            old_content = self._blocks.get_version(uow.session, uid, version)
            current_content = self._files.read(block.meta.path)
            self._blocks.add_version(
                uow.session,
                uid,
                block.meta.version,
                current_content,
                f"перед откатом к v{version}",
                None,
                now,
            )
            self._files.write_raw(block.meta.path, old_content)
            meta_raw, _ = parse_markdown(old_content)
            restored = BlockMeta(
                **{
                    **_dict_of(block.meta),
                    "title": meta_raw.get("title", block.meta.title),
                    "kind": meta_raw.get("kind", block.meta.kind),
                    "summary": meta_raw.get("summary") or "",
                    "tags": tuple(meta_raw.get("tags") or ()),
                    "version": block.meta.version + 1,
                    "updated": now,
                }
            )
            self._blocks.update_row(uow.session, restored)
            uow.emit(BlockUpdated(block_uid=uid, version=restored.version, reason=reason))
            return Block(meta=restored, content=old_content)

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
            return self._blocks.versions(uow.session, uid)

    def get_version_content(self, uid: str, version: int) -> str:
        """Полный MD-контент версии."""
        with self._uow() as uow:
            return self._blocks.get_version(uow.session, uid, version)

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

    # --- категории ---

    def category_tree(self) -> list[dict]:
        """Дерево категорий со счётчиками (включая подкатегории)."""
        with self._uow() as uow:
            cats = self._cats.all(uow.session)
            counts = self._cats.counts_by_prefix(uow.session)
        total: dict[str, int] = {}
        for cat in cats:
            for anc in _with_ancestors(cat.path):
                total[anc] = total.get(anc, 0) + counts.get(cat.path, 0)
        nodes = {
            c.path: {
                "path": c.path,
                "title": c.title,
                "color": c.color,
                "icon": c.icon,
                "count": total.get(c.path, 0),
                "children": [],
            }
            for c in cats
        }
        roots = []
        for c in cats:
            node = nodes[c.path]
            if c.parent_path and c.parent_path in nodes:
                nodes[c.parent_path]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def ensure_categories_default(self) -> None:
        """Записать стартовое дерево, если категорий нет вообще (миграция/первый старт)."""
        with self._uow() as uow:
            existing = self._cats.all(uow.session)
            if existing:
                return
            cats = default_categories()
            for cat in cats:
                self._cats.ensure(uow.session, cat)
        self._files.write_categories(default_categories())

    def create_category(
        self, path: str, title: str, color: str | None = None, icon: str | None = None, sort: int = 0
    ) -> Category:
        """Создать узел дерева (агент может, если ни один не подходит); пишет YAML и индекс."""
        normalized = normalize_category_path(path)
        parent = "/".join(normalized.split("/")[:-1]) or None
        cat = Category(path=normalized, title=title, parent_path=parent, color=color, icon=icon, sort=sort)
        with self._uow() as uow:
            self._cats.ensure(uow.session, cat)
            cats = self._cats.all(uow.session)
        self._files.write_categories(cats)
        return cat

    def update_category(self, path: str, **kwargs: Any) -> Category:
        """Переименовать/перекрасить категорию."""
        with self._uow() as uow:
            cat = self._cats.update(uow.session, path, **kwargs)
            cats = self._cats.all(uow.session)
        self._files.write_categories(cats)
        return cat

    def list_categories(self) -> list[Category]:
        """Плоский список категорий."""
        with self._uow() as uow:
            return self._cats.all(uow.session)

    def set_block_category(self, uid: str, path: str | None, confirm: bool) -> Block:
        """Поставить блоку категорию; confirm=true — подтверждение пользователем (правит frontmatter)."""
        now = now_iso(self._clock)
        if path:
            normalized = normalize_category_path(path)
            self._ensure_category(normalized)
        else:
            normalized = None
        with self._uow() as uow:
            block = self._blocks.get(uow.session, uid)
            content = self._files.read(block.meta.path)
            meta_raw, body = parse_markdown(content)
            meta_raw["category"] = normalized
            meta_raw["category_status"] = "confirmed" if confirm else "suggested"
            meta_raw["updated"] = now
            new_content = _assemble(meta_raw, body)
            self._files.write_raw(block.meta.path, new_content)
            from dataclasses import replace

            new_meta = replace(
                block.meta,
                category_path=normalized,
                category_status="confirmed" if confirm else "suggested",
                updated=now,
            )
            self._blocks.update_row(uow.session, new_meta)
            if confirm:
                uow.emit(CategoryConfirmed(block_uid=uid, path=normalized or ""))
            return Block(meta=new_meta, content=new_content)

    # --- reindex ---

    def reindex(self) -> dict:
        """Пересобрать индекс знаний из kb/ (после ручной правки MD)."""
        from .domain import extract_links

        created, updated = 0, 0
        with self._uow() as uow:
            known = set(self._blocks.uids(uow.session))
            for stem in self._files.list_stems():
                try:
                    meta = self._files.read_meta(stem)
                except (NotFound, ValueError) as e:
                    log.warning("reindex: пропуск %s: %s", stem, e)
                    continue
                meta = BlockMeta(
                    **{
                        **_dict_of(meta),
                        "path": stem,
                        "links": extract_links(self._files.read(stem).split("---", 2)[-1]),
                    }
                )
                if meta.uid in known:
                    self._blocks.update_row(uow.session, meta)
                    updated += 1
                else:
                    self._blocks.save(uow.session, meta)
                    created += 1
        return {"ok": True, "created": created, "updated": updated}

    # --- генерация блока агентами ---

    def generate_from_transcript(self, session: dict) -> BlockDraft:
        """Собрать BlockDraft из транскрипта сессии (block_writer + categorizer)."""
        if self._runtime is None:
            raise NotFound("агентный рантайм недоступен")
        from .agents import block_writer, categorizer

        transcript = session.get("transcript") or []
        dialog = "\n".join(
            f"[{e['state']}/{e['event']}] {json.dumps(e.get('payload') or {}, ensure_ascii=False)}"
            for e in transcript
        )
        existing = self.list_blocks(limit=50)
        existing_brief = "\n".join(f"- {m.uid}: {m.title}" for m in existing) or "(пусто)"
        cats = "\n".join(f"- {c.path}" for c in self.list_categories()) or "(пусто)"
        profile_brief = self._profile_brief() if self._profile else ""
        extra = (
            f"Существующие блоки (links — только эти uid):\n{existing_brief}\n\nДерево категорий:\n{cats}"
            + (f"\n\n{profile_brief}" if profile_brief else "")
        )
        ctx = AgentContext(system_extra=extra)
        out = run_coro_sync(self._runtime.run_structured(block_writer, ctx, f"Транскрипт сессии:\n{dialog}"))
        draft = _writer_out_to_draft(out, kind=session.get("block_kind", "lesson"))
        try:
            cat_ctx = AgentContext(system_extra=f"Дерево:\n{cats}")
            cat_out = run_coro_sync(
                self._runtime.run_structured(categorizer, cat_ctx, f"Блок: {draft.title}\n{draft.summary}")
            )
            path = cat_out.path
            if getattr(cat_out, "new_category_title", None):
                self.create_category(path, cat_out.new_category_title)
            from dataclasses import replace

            draft = replace(draft, category_suggestion=path)
        except Exception:  # noqa: BLE001 — категория не критична
            log.info("categorizer не сработал, категория не проставлена")
        return draft

    def generate_runbook(self, session: dict, lesson_uid: str) -> BlockDraft:
        """Собрать runbook-драфт из practice_log транскрипта (runbook_writer)."""
        if self._runtime is None:
            raise NotFound("агентный рантайм недоступен")
        from dataclasses import replace

        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import runbook_writer

        transcript = session.get("transcript") or []
        dialog = "\n".join(
            f"[{e['state']}/{e['event']}] {json.dumps(e.get('payload') or {}, ensure_ascii=False)}"
            for e in transcript
        )
        ctx = AgentContext(system_extra=f"Связанный урок: {lesson_uid}\nПрофиль:\n{self._profile_brief()}")
        out = run_coro_sync(
            self._runtime.run_structured(runbook_writer, ctx, f"Транскрипт сессии:\n{dialog}")
        )
        draft = _writer_out_to_draft(out, kind="runbook")
        return replace(draft, links=(lesson_uid,))

    def _profile_brief(self) -> str:
        try:
            return (
                f"Профиль пользователя:\n{self._profile.machines_brief()}\n{self._profile.learning_brief()}"
            )
        except Exception:  # noqa: BLE001
            return ""

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
        """Разобрать текущий MD обратно в драфт (для патчей)."""
        from .domain import BlockSource

        body = content.split("---", 2)[-1]
        theses = _section_items(body, "Тезисы")
        examples = [x.strip("«» ") for x in _section_items(body, "Как я это понял")]
        weak = [
            w[len("> [!WARNING]\n> ") :] if w.startswith("> [!WARNING]") else w
            for w in _section_items(body, "Дозакрепить")
        ]
        mermaid = None
        if "```mermaid\n" in body:
            mermaid = body.split("```mermaid\n", 1)[1].split("\n```", 1)[0]
        return BlockDraft(
            title=meta_raw.get("title", "Без названия"),
            summary=meta_raw.get("summary") or "",
            kind=meta_raw.get("kind", "lesson"),
            theses=tuple(theses),
            my_examples=tuple(examples),
            mermaid=mermaid,
            weak_spots=tuple(w for w in weak if w),
            open_questions=tuple(_section_items(body, "Вопросы на потом")),
            links=tuple(meta_raw.get("links") or ()),
            tags=tuple(meta_raw.get("tags") or ()),
            category_suggestion=meta_raw.get("category"),
            sources=tuple(
                BlockSource(source=s.get("source", ""), chapter=s.get("chapter"), title=s.get("title", ""))
                for s in (meta_raw.get("sources") or [])
            ),
        )


def _section_items(body: str, section: str) -> list[str]:
    """Пункты секции «## section» до следующего заголовка."""
    import re

    m = re.search(rf"^## {re.escape(section)}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not m:
        return []
    items = []
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if line.startswith(("- ", "> ")) or (line and line[0].isdigit() and ". " in line[:5]):
            items.append(line.lstrip("- ").lstrip("> "))
    return items


def _with_ancestors(path: str) -> list[str]:
    """Путь и все его префиксы."""
    parts = path.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _writer_out_to_draft(out, kind: str) -> BlockDraft:
    """Выход block_writer (pydantic) → доменный BlockDraft."""
    from .domain import BlockSource, Concept, PracticeStep

    return BlockDraft(
        title=out.title,
        summary=out.summary,
        kind=kind if kind in {"lesson", "note", "runbook"} else "lesson",
        concepts=tuple(Concept(c["term"], c["definition"]) for c in out.concepts),
        theses=tuple(out.theses),
        my_examples=tuple(out.my_examples),
        mermaid=out.mermaid,
        practice=tuple(
            PracticeStep(p["machine"], p["command"], p["explanation"], p.get("result")) for p in out.practice
        ),
        weak_spots=tuple(out.weak_spots),
        open_questions=tuple(out.open_questions),
        links=tuple(link for link in out.links if link.startswith("blk_")),
        tags=tuple(out.tags),
        category_suggestion=out.category_suggestion,
        # источник — только реальный uid (модель любит подставить заголовок)
        sources=tuple(
            BlockSource(source=s["source"], chapter=s.get("chapter"), title=s.get("title", ""))
            for s in getattr(out, "sources", []) or []
            if str(s.get("source", "")).startswith("src_")
        ),
    )


def _dict_of(meta: BlockMeta) -> dict:
    return {
        "uid": meta.uid,
        "title": meta.title,
        "kind": meta.kind,
        "summary": meta.summary,
        "category_path": meta.category_path,
        "category_status": meta.category_status,
        "tags": meta.tags,
        "sources": meta.sources,
        "session_uid": meta.session_uid,
        "conversation_uid": meta.conversation_uid,
        "activity_uid": meta.activity_uid,
        "version": meta.version,
        "created": meta.created,
        "updated": meta.updated,
        "links": meta.links,
        "weak_spots_count": meta.weak_spots_count,
        "path": meta.path,
    }


def _assemble(meta_raw: dict, body: str) -> str:
    """Склеить frontmatter + тело обратно в MD."""
    import yaml

    fm = yaml.safe_dump(meta_raw, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body}"
