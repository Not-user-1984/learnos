"""MD-хранилище базы знаний: kb/blocks/*.md + kb/categories.yaml. Атомарная запись."""

import os
import tempfile
from pathlib import Path

import yaml

from ....kernel.errors import NotFound
from ..domain import BlockDraft, BlockMeta, Category, draft_to_markdown, parse_markdown


class MdBlockStore:
    """Чтение/запись MD-блоков и дерева категорий в kb/. Файл — источник истины."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb = Path(kb_dir)
        self._blocks_dir = self._kb / "blocks"

    @property
    def blocks_dir(self) -> Path:
        self._blocks_dir.mkdir(parents=True, exist_ok=True)
        return self._blocks_dir

    def file_name(self, uid: str, title: str, created_name: str | None = None) -> Path:
        """Путь файла: <uid>_<slug>.md; при наличии старого имени — переиспользуем его."""
        from ..domain import slugify

        if created_name:
            return self.blocks_dir / f"{created_name}.md"
        slug = slugify(title)
        return self.blocks_dir / (f"{uid}_{slug}.md" if slug else f"{uid}.md")

    def write(self, uid: str, draft: BlockDraft, meta_extra: dict, existing_name: str | None = None) -> str:
        """Атомарно записать MD-файл (temp + os.replace); вернуть имя файла без .md."""
        content = draft_to_markdown(uid, draft, meta_extra)
        path = self.file_name(uid, draft.title, existing_name)
        self._atomic_write(path, content)
        return path.stem

    def read(self, file_stem: str) -> str:
        """Прочитать файл по имени без расширения."""
        path = self.blocks_dir / f"{file_stem}.md"
        if not path.exists():
            raise NotFound(f"файл блока '{file_stem}' не найден")
        return path.read_text(encoding="utf-8")

    def read_meta(self, file_stem: str) -> BlockMeta:
        """Метаданные блока из frontmatter + ссылки из тела."""
        from ..domain import BlockSource, count_weak_spots, extract_links

        content = self.read(file_stem)
        meta_raw, body = parse_markdown(content)
        return BlockMeta(
            uid=meta_raw.get("id", file_stem),
            title=meta_raw.get("title", ""),
            kind=meta_raw.get("kind", "lesson"),
            summary=meta_raw.get("summary") or "",
            category_path=meta_raw.get("category"),
            category_status=meta_raw.get("category_status", "suggested"),
            tags=tuple(meta_raw.get("tags") or ()),
            sources=tuple(
                BlockSource(source=s.get("source", ""), chapter=s.get("chapter"), title=s.get("title", ""))
                for s in (meta_raw.get("sources") or [])
            ),
            session_uid=meta_raw.get("session"),
            conversation_uid=meta_raw.get("conversation"),
            activity_uid=meta_raw.get("activity"),
            version=meta_raw.get("version", 1),
            created=str(meta_raw.get("created") or ""),
            updated=str(meta_raw.get("updated") or ""),
            links=extract_links(body),
            weak_spots_count=count_weak_spots(body),
            path=str(self.blocks_dir / f"{file_stem}.md"),
        )

    def write_raw(self, file_stem: str, content: str) -> None:
        """Перезаписать файл целиком (правка/откат)."""
        self._atomic_write(self.blocks_dir / f"{file_stem}.md", content)

    def list_stems(self) -> list[str]:
        """Все имена блоков на диске."""
        return sorted(p.stem for p in self.blocks_dir.glob("*.md"))

    # --- категории ---

    def read_categories(self) -> list[Category]:
        """Дерево из kb/categories.yaml (пусто, если файла нет)."""
        path = self._kb / "categories.yaml"
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        return _flatten_categories(raw, parent=None)

    def write_categories(self, categories: list[Category]) -> None:
        """Записать дерево категорий (плоский список → вложенный YAML)."""
        tree = _build_tree(categories)
        self._atomic_write(
            self._kb / "categories.yaml", yaml.safe_dump(tree, allow_unicode=True, sort_keys=False)
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _flatten_categories(raw: list, parent: str | None) -> list[Category]:
    out: list[Category] = []
    for node in raw:
        out.append(
            Category(
                path=node["path"],
                title=node.get("title", node["path"].split("/")[-1]),
                parent_path=parent,
                color=node.get("color"),
                icon=node.get("icon"),
                sort=node.get("sort", 0),
            )
        )
        out.extend(_flatten_categories(node.get("children") or [], node["path"]))
    return out


def _build_tree(categories: list[Category]) -> list[dict]:
    by_parent: dict[str | None, list[Category]] = {}
    for c in categories:
        by_parent.setdefault(c.parent_path, []).append(c)

    def _node(c: Category) -> dict:
        node: dict = {"path": c.path, "title": c.title}
        if c.color:
            node["color"] = c.color
        if c.icon:
            node["icon"] = c.icon
        if c.sort:
            node["sort"] = c.sort
        children = [_node(ch) for ch in sorted(by_parent.get(c.path, []), key=lambda x: (x.sort, x.title))]
        if children:
            node["children"] = children
        return node

    return [_node(c) for c in sorted(by_parent.get(None, []), key=lambda x: (x.sort, x.title))]
