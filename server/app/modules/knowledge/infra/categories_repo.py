"""Репозиторий категорий: дерево и счётчики (B-009: разрез sql_repo)."""

from __future__ import annotations

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from ....kernel.errors import Conflict, NotFound
from ..domain import Category
from .tables import blocks, categories


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
