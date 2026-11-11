"""Категории знаний (B-009): дерево, CRUD, привязка блоков — вынесено из service."""

from __future__ import annotations

from typing import Any

from ....kernel.clock import now_iso
from ..domain import Block, Category, default_categories, normalize_category_path, parse_markdown
from ..domain import assemble_frontmatter as _assemble
from ..domain import with_ancestors as _with_ancestors
from ..events import CategoryConfirmed


class CategoryUseCases:
    """Дерево категорий: чтение, создание, подкатегория блока (перенос из service)."""

    def __init__(self, svc) -> None:
        self._svc = svc

    def tree(self) -> list[dict]:
        """Дерево категорий со счётчиками (включая подкатегории)."""
        with self._svc._uow() as uow:  # noqa: SLF001
            cats = self._svc._cats.all(uow.session)  # noqa: SLF001
            counts = self._svc._cats.counts_by_prefix(uow.session)  # noqa: SLF001
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

    def ensure_default(self) -> None:
        """Записать стартовое дерево, если категорий нет; YAML восстановить из БД."""
        with self._svc._uow() as uow:  # noqa: SLF001
            existing = self._svc._cats.all(uow.session)  # noqa: SLF001
            if existing:
                if not (self._svc._files.blocks_dir.parent / "categories.yaml").exists():  # noqa: SLF001
                    self._svc._files.write_categories(existing)  # noqa: SLF001
                return
            for cat in default_categories():
                self._svc._cats.ensure(uow.session, cat)  # noqa: SLF001
        self._svc._files.write_categories(default_categories())  # noqa: SLF001

    def create(
        self, path: str, title: str, color: str | None = None, icon: str | None = None, sort: int = 0
    ) -> Category:
        """Создать узел дерева; пишет YAML и индекс."""
        normalized = normalize_category_path(path)
        parent = "/".join(normalized.split("/")[:-1]) or None
        cat = Category(path=normalized, title=title, parent_path=parent, color=color, icon=icon, sort=sort)
        with self._svc._uow() as uow:  # noqa: SLF001
            self._svc._cats.ensure(uow.session, cat)  # noqa: SLF001
            cats = self._svc._cats.all(uow.session)  # noqa: SLF001
        self._svc._files.write_categories(cats)  # noqa: SLF001
        return cat

    def update(self, path: str, **kwargs: Any) -> Category:
        """Переименовать/перекрасить категорию."""
        with self._svc._uow() as uow:  # noqa: SLF001
            cat = self._svc._cats.update(uow.session, path, **kwargs)  # noqa: SLF001
            cats = self._svc._cats.all(uow.session)  # noqa: SLF001
        self._svc._files.write_categories(cats)  # noqa: SLF001
        return cat

    def list(self) -> list[Category]:
        """Плоский список категорий."""
        with self._svc._uow() as uow:  # noqa: SLF001
            return self._svc._cats.all(uow.session)  # noqa: SLF001

    def set_block_category(self, uid: str, path: str | None, confirm: bool) -> Block:
        """Поставить блоку категорию; confirm=true — подтверждение пользователем."""
        now = now_iso(self._svc._clock)  # noqa: SLF001
        if path:
            normalized = normalize_category_path(path)
            self._svc._ensure_category(normalized)  # noqa: SLF001
        else:
            normalized = None
        with self._svc._uow() as uow:  # noqa: SLF001
            block = self._svc._blocks.get(uow.session, uid)  # noqa: SLF001
            content = self._svc._files.read(block.meta.path)  # noqa: SLF001
            meta_raw, body = parse_markdown(content)
            meta_raw["category"] = normalized
            meta_raw["category_status"] = "confirmed" if confirm else "suggested"
            meta_raw["updated"] = now
            new_content = _assemble(meta_raw, body)
            self._svc._files.write_raw(block.meta.path, new_content)  # noqa: SLF001
            from dataclasses import replace

            new_meta = replace(
                block.meta,
                category_path=normalized,
                category_status="confirmed" if confirm else "suggested",
                updated=now,
            )
            self._svc._blocks.update_row(uow.session, new_meta)  # noqa: SLF001
            if confirm:
                uow.emit(CategoryConfirmed(block_uid=uid, path=normalized or ""))
            return Block(meta=new_meta, content=new_content)
