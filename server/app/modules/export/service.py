"""Сервис экспорта: склеенный Markdown и ZIP (Obsidian-совместимый)."""

import io
import re
import zipfile
from datetime import UTC, datetime

from ...kernel.errors import NotFound, ValidationFailed

WIKILINK = re.compile(r"\[\[(blk_[0-9a-f]+)\]\]")


class ExportService:
    """Сборка выгрузок по scope: block | category | course | source | all."""

    def __init__(self, knowledge, library, courses) -> None:
        self._kb = knowledge
        self._lib = library
        self._courses = courses

    def markdown(self, scope: str, ref: str | None = None, max_chars: int | None = None) -> dict:
        """Склеенный MD: шапка, оглавление, блоки по порядку; wikilinks → якоря."""
        blocks = self._collect(scope, ref)
        if not blocks:
            raise NotFound("для выгрузки не нашлось блоков")
        titles = {b.meta.uid: b.meta.title for b in blocks}
        header = (
            f"# Выгрузка LearnOS — {scope}"
            + (f": {ref}" if ref else "")
            + f"\n\nДата: {datetime.now(UTC).isoformat(timespec='seconds')} · блоков: {len(blocks)}\n"
        )
        toc = "\n## Оглавление\n\n" + "\n".join(f"- [{t}](#{_anchor(t)})" for t in titles.values())
        parts = [header, toc]
        for b in blocks:
            kind_label = "урок" if b.meta.kind == "lesson" else "конспект"
            meta_line = f"*{kind_label} · {b.meta.created[:10]} · v{b.meta.version}"
            if b.meta.category_path:
                meta_line += f" · {b.meta.category_path}"
            meta_line += "*\n"
            body = WIKILINK.sub(
                lambda m: _link_md_anchor(m, titles),
                b.content,
            )
            parts.append(f"\n---\n\n{body}\n{meta_line}")
        text = "\n".join(parts)
        truncated = False
        if max_chars and len(text) > max_chars:
            text = (
                text[:max_chars]
                + "\n\n…(обрезано по max_chars; запросите выгрузку частями или без ограничения)"
            )
            truncated = True
        return {
            "filename": f"learnos-{scope}.md",
            "content": text,
            "blocks": len(blocks),
            "truncated": truncated,
        }

    def zip(self, scope: str, ref: str | None = None) -> bytes:
        """ZIP: дерево папок по категориям, блоки с frontmatter, README, categories.yaml."""
        blocks = self._collect(scope, ref)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            titles = {b.meta.uid: b.meta.title for b in blocks}
            index_lines = []
            for b in blocks:
                cat = (b.meta.category_path or "_uncategorized").replace("/", " · ")
                name = self._kb.get_block(b.meta.uid).meta.path or b.meta.uid
                path = f"{cat}/{name}.md"
                content = WIKILINK.sub(
                    lambda m: _link_md_wikilink(m, titles),
                    b.content,
                )
                zf.writestr(path, content)
                index_lines.append(f"- [{b.meta.title}]({path})")
            zf.writestr(
                "README.md",
                f"# Выгрузка LearnOS ({scope})\n\nДата: {datetime.now(UTC).isoformat(timespec='seconds')}\n\n"
                + "\n".join(index_lines),
            )
            categories_yaml = self._kb._files._kb / "categories.yaml"  # noqa: SLF001 — экспорт файла категорий как есть
            if categories_yaml.exists():
                zf.writestr("categories.yaml", categories_yaml.read_text(encoding="utf-8"))
            if scope == "course" and ref:
                course = self._courses.get_course(ref)
                zf.writestr("course.md", self._course_md(course))
            if scope == "source" and ref:
                src = self._lib.get_source(ref)
                zf.writestr("source.md", self._source_md(src))
        return buf.getvalue()

    def _collect(self, scope: str, ref: str | None):
        """Блоки для scope: block | category | course | source | all."""
        if scope == "block":
            return [self._kb.get_block(ref or "")]
        if scope == "category":
            return [self._kb.get_block(m.uid) for m in self._kb.list_blocks(category=ref, limit=500)]
        if scope == "source":
            return [self._kb.get_block(m.uid) for m in self._kb.list_blocks(source=ref, limit=500)]
        if scope == "course":
            course = self._courses.get_course(ref or "")
            uids = [
                i["block_uid"]
                for i in course.get("items", [])
                if i["item_type"] == "block" and i["block_uid"]
            ]
            return [self._kb.get_block(u) for u in uids]
        if scope == "all":
            return [self._kb.get_block(m.uid) for m in self._kb.list_blocks(limit=1000)]
        raise ValidationFailed(f"неизвестный scope: {scope}")

    @staticmethod
    def _course_md(course: dict) -> str:
        lines = [f"# {course['title']}", "", f"Тема: {course['topic']} · статус: {course['status']}", ""]
        for item in course.get("items", []):
            mark = "x" if item.get("done") else " "
            lines.append(f"- [{mark}] {item.get('title', '?')} — {item.get('hint', '')}")
        return "\n".join(lines)

    @staticmethod
    def _source_md(src: dict) -> str:
        lines = [
            f"# {src['title']}",
            "",
            f"Вид: {src['kind']} · статус: {src['status']}",
            "",
            src.get("summary") or "",
            "",
        ]
        for ch in src.get("chapters", []):
            lines.append(f"## Глава {ch['idx']}. {ch['title']}")
            lines.append(ch.get("summary") or "")
            lines.append("")
        return "\n".join(lines)


def _anchor(title: str) -> str:
    """Якорь заголовка в MD (латиница/цифры/дефисы)."""
    from ..knowledge.domain import slugify

    return slugify(title).lower()


def _link_md_anchor(m: re.Match, titles: dict[str, str]) -> str:
    """Wikilink → MD-ссылка на якорь заголовка блока (для склеенной выгрузки)."""
    if m.group(1) not in titles:
        return "_(блок вне выгрузки)_"
    title = titles.get(m.group(1), m.group(1))
    return f"[{titles.get(m.group(1), 'блок вне выгрузки')}](#{_anchor(title)})"


def _link_md_wikilink(m: re.Match, titles: dict[str, str]) -> str:
    """Wikilink → Obsidian-wikilink с читаемым заголовком (для ZIP-выгрузки)."""
    if m.group(1) not in titles:
        return "_(блок вне выгрузки)_"
    return f"[[{m.group(1)}_{_slug(titles.get(m.group(1), ''))}|{titles.get(m.group(1), m.group(1))}]]"


def _slug(title: str) -> str:
    from ..knowledge.domain import slugify

    return slugify(title)
