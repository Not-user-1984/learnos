"""SQL-репозитории knowledge: блоки, версии, категории (SQLAlchemy Core)."""

from __future__ import annotations

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import Conflict, NotFound
from ..domain import Block, BlockMeta, BlockSource, Category
from .tables import block_links, block_sources, block_tags, block_versions, blocks, categories


class BlockRepository:
    """Индекс блоков (строки blocks + связанные таблицы)."""

    def save(self, session: Session, meta: BlockMeta) -> None:
        """Вставить или обновить индекс блока вместе с тегами, источниками и связями."""
        session.execute(
            insert(blocks).values(
                block_uid=meta.uid,
                kind=meta.kind,
                title=meta.title,
                summary=meta.summary,
                category_path=meta.category_path,
                category_status=meta.category_status,
                path=meta.path,
                session_uid=meta.session_uid,
                conversation_uid=meta.conversation_uid,
                activity_uid=meta.activity_uid,
                weak_spots_count=meta.weak_spots_count,
                version=meta.version,
                created_at=meta.created or meta.updated,
                updated_at=meta.updated,
            )
        )
        self._rewrite_relations(session, meta)

    def update_row(self, session: Session, meta: BlockMeta) -> None:
        """Обновить существующую строку индекса."""
        session.execute(
            update(blocks)
            .where(blocks.c.block_uid == meta.uid)
            .values(
                kind=meta.kind,
                title=meta.title,
                summary=meta.summary,
                category_path=meta.category_path,
                category_status=meta.category_status,
                path=meta.path,
                weak_spots_count=meta.weak_spots_count,
                version=meta.version,
                updated_at=meta.updated,
            )
        )
        session.execute(delete(block_tags).where(block_tags.c.block_uid == meta.uid))
        session.execute(delete(block_sources).where(block_sources.c.block_uid == meta.uid))
        session.execute(delete(block_links).where(block_links.c.from_uid == meta.uid))
        self._rewrite_relations(session, meta)

    def _rewrite_relations(self, session: Session, meta: BlockMeta) -> None:
        if meta.tags:
            session.execute(insert(block_tags), [{"block_uid": meta.uid, "tag": t} for t in meta.tags])
        if meta.sources:
            session.execute(
                insert(block_sources),
                [
                    {"block_uid": meta.uid, "source_uid": s.source, "chapter_idx": s.chapter}
                    for s in meta.sources
                ],
            )
        if meta.links:
            session.execute(insert(block_links), [{"from_uid": meta.uid, "to_uid": t} for t in meta.links])

    def get(self, session: Session, uid: str) -> Block:
        """Блок по uid (метаданные + счётчик версий + обратные связи)."""
        row = session.execute(select(blocks).where(blocks.c.block_uid == uid)).first()
        if row is None:
            raise NotFound(f"блок '{uid}' не найден")
        meta = self._row_to_meta(row)
        versions_count = session.execute(
            select(func.count()).where(block_versions.c.block_uid == uid)
        ).scalar_one()
        back = [
            r[0] for r in session.execute(select(block_links.c.from_uid).where(block_links.c.to_uid == uid))
        ]
        meta = BlockMeta(
            **{**_meta_dict(meta), "versions_count": int(versions_count or 0), "back_links": tuple(back)}
        )
        return Block(meta=meta, content="")

    def list(
        self,
        session: Session,
        *,
        category: str | None = None,
        tag: str | None = None,
        kind: str | None = None,
        source: str | None = None,
        status: str | None = None,
        q: str | None = None,
        sort: str = "created",
        order: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> list[BlockMeta]:
        """Список блоков с фильтрами; category включает подкатегории."""
        stmt = select(blocks)
        if category:
            # категория включает подкатегории: programming/python ловит и programming/python/oop
            stmt = stmt.where(
                (blocks.c.category_path == category) | (blocks.c.category_path.like(f"{category}/%"))
            )
        if kind:
            stmt = stmt.where(blocks.c.kind == kind)
        if source:
            stmt = stmt.where(
                blocks.c.block_uid.in_(
                    select(block_sources.c.block_uid).where(block_sources.c.source_uid == source)
                )
            )
        if tag:
            stmt = stmt.where(
                blocks.c.block_uid.in_(select(block_tags.c.block_uid).where(block_tags.c.tag == tag))
            )
        if status == "inbox":
            stmt = stmt.where(blocks.c.category_status == "suggested")
        if q:
            needle = f"%{q.lower()}%"
            stmt = stmt.where(
                func.lower(blocks.c.title).like(needle)
                | func.lower(func.coalesce(blocks.c.summary, "")).like(needle)
            )
        column = {
            "created": blocks.c.created_at,
            "updated": blocks.c.updated_at,
            "title": blocks.c.title,
            "weak": blocks.c.weak_spots_count,
        }.get(sort, blocks.c.created_at)
        stmt = stmt.order_by(column.desc() if order == "desc" else column.asc()).limit(limit).offset(offset)
        return [self._row_to_meta(r) for r in session.execute(stmt)]

    def count(self, session: Session) -> int:
        return int(session.execute(select(func.count()).select_from(blocks)).scalar_one())

    def uids(self, session: Session) -> list[str]:
        return [r[0] for r in session.execute(select(blocks.c.block_uid))]

    def delete(self, session: Session, uid: str) -> None:
        """Удалить блок целиком: индекс, теги, источники, свои связи, версии."""
        session.execute(delete(blocks).where(blocks.c.block_uid == uid))
        session.execute(delete(block_tags).where(block_tags.c.block_uid == uid))
        session.execute(delete(block_sources).where(block_sources.c.block_uid == uid))
        session.execute(delete(block_links).where(block_links.c.from_uid == uid))
        session.execute(delete(block_versions).where(block_versions.c.block_uid == uid))

    def tags_counts(self, session: Session) -> dict[str, int]:
        rows = session.execute(select(block_tags.c.tag, func.count()).group_by(block_tags.c.tag)).all()
        return {r[0]: int(r[1]) for r in rows}

    def add_version(
        self,
        session: Session,
        uid: str,
        version: int,
        content: str,
        reason: str | None,
        conversation_uid: str | None,
        created_at: str,
    ) -> None:
        """Сохранить предыдущую версию блока."""
        session.execute(
            insert(block_versions).values(
                block_uid=uid,
                version=version,
                content=content,
                reason=reason,
                conversation_uid=conversation_uid,
                created_at=created_at,
            )
        )

    def get_version(self, session: Session, uid: str, version: int) -> str:
        """Полный MD-контент указанной версии."""
        row = session.execute(
            select(block_versions.c.content).where(
                block_versions.c.block_uid == uid, block_versions.c.version == version
            )
        ).first()
        if row is None:
            raise NotFound(f"версия {version} блока '{uid}' не найдена")
        return row[0]

    def versions(self, session: Session, uid: str) -> list[dict]:
        """История версий (новые сверху)."""
        rows = session.execute(
            select(
                block_versions.c.version,
                block_versions.c.reason,
                block_versions.c.conversation_uid,
                block_versions.c.created_at,
                block_versions.c.content,
            )
            .where(block_versions.c.block_uid == uid)
            .order_by(block_versions.c.version.desc())
        ).all()
        return [
            {"version": r[0], "reason": r[1], "conversation_uid": r[2], "created_at": r[3], "size": len(r[4])}
            for r in rows
        ]

    @staticmethod
    def _row_to_meta(row) -> BlockMeta:
        return BlockMeta(
            uid=row.block_uid,
            title=row.title,
            kind=row.kind,
            summary=row.summary or "",
            category_path=row.category_path,
            category_status=row.category_status,
            tags=(),
            sources=(),
            session_uid=row.session_uid,
            conversation_uid=row.conversation_uid,
            activity_uid=row.activity_uid,
            version=row.version,
            created=row.created_at,
            updated=row.updated_at,
            weak_spots_count=row.weak_spots_count,
            path=row.path,
        )

    def meta_with_relations(self, session: Session, meta: BlockMeta) -> BlockMeta:
        """Дополнить метаданные тегами/источниками/связями из таблиц."""
        tags = [
            r[0] for r in session.execute(select(block_tags.c.tag).where(block_tags.c.block_uid == meta.uid))
        ]
        src_rows = session.execute(
            select(block_sources.c.source_uid, block_sources.c.chapter_idx).where(
                block_sources.c.block_uid == meta.uid
            )
        ).all()
        links = [
            r[0]
            for r in session.execute(select(block_links.c.to_uid).where(block_links.c.from_uid == meta.uid))
        ]
        return BlockMeta(
            **{
                **_meta_dict(meta),
                "tags": tuple(tags),
                "sources": tuple(BlockSource(source=r[0], chapter=r[1]) for r in src_rows),
                "links": tuple(links),
            }
        )


def _meta_dict(meta: BlockMeta) -> dict:
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


class CategoryRepository:
    """Индекс категорий: синхронизирован с kb/categories.yaml."""

    def all(self, session: Session) -> list[Category]:
        rows = session.execute(select(categories).order_by(categories.c.path)).all()
        return [
            Category(
                path=r.path, title=r.title, parent_path=r.parent_path, color=r.color, icon=r.icon, sort=r.sort
            )
            for r in rows
        ]

    def get(self, session: Session, path: str) -> Category:
        row = session.execute(select(categories).where(categories.c.path == path)).first()
        if row is None:
            raise NotFound(f"категория '{path}' не найдена")
        return Category(
            path=row.path,
            title=row.title,
            parent_path=row.parent_path,
            color=row.color,
            icon=row.icon,
            sort=row.sort,
        )

    def ensure(self, session: Session, cat: Category) -> None:
        """Создать категорию, если нет (идемпотентно)."""
        existing = session.execute(select(categories).where(categories.c.path == cat.path)).first()
        if existing is None:
            if cat.parent_path:
                parent = session.execute(
                    select(categories).where(categories.c.path == cat.parent_path)
                ).first()
                if parent is None:
                    raise NotFound(f"родительская категория '{cat.parent_path}' не найдена")
            session.execute(
                insert(categories).values(
                    path=cat.path,
                    title=cat.title,
                    parent_path=cat.parent_path,
                    color=cat.color,
                    icon=cat.icon,
                    sort=cat.sort,
                )
            )

    def update(
        self,
        session: Session,
        path: str,
        *,
        title: str | None,
        color: str | None,
        icon: str | None,
        sort: int | None,
    ) -> Category:
        cat = self.get(session, path)
        from dataclasses import replace

        new_cat = replace(
            cat,
            title=title or cat.title,
            color=color if color is not None else cat.color,
            icon=icon if icon is not None else cat.icon,
            sort=sort if sort is not None else cat.sort,
        )
        session.execute(
            update(categories)
            .where(categories.c.path == path)
            .values(title=new_cat.title, color=new_cat.color, icon=new_cat.icon, sort=new_cat.sort)
        )
        return new_cat

    def delete(self, session: Session, path: str) -> None:
        count = session.execute(
            select(func.count()).select_from(blocks).where(blocks.c.category_path == path)
        ).scalar_one()
        if count:
            raise Conflict(f"в категории '{path}' {count} блок(ов) — сначала переместите их")
        session.execute(delete(categories).where(categories.c.path == path))

    def counts_by_prefix(self, session: Session) -> dict[str, int]:
        """Число блоков по точному пути категории."""
        rows = session.execute(
            select(blocks.c.category_path, func.count()).group_by(blocks.c.category_path)
        ).all()
        return {r[0]: int(r[1]) for r in rows if r[0]}

    def sync_all(self, session: Session, cats: list[Category]) -> None:
        """Полная перезапись индекса категорий из YAML."""
        session.execute(delete(categories))
        if cats:
            session.execute(
                insert(categories),
                [
                    {
                        "path": c.path,
                        "title": c.title,
                        "parent_path": c.parent_path,
                        "color": c.color,
                        "icon": c.icon,
                        "sort": c.sort,
                    }
                    for c in cats
                ],
            )
