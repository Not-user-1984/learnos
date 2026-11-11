"""Домен базы знаний: BlockDraft, правила версий и патчей, сборка/разбор MD-формата v2.

Чистый Python: без FastAPI, SQLAlchemy, pydantic, файловой системы.
"""

import re
from dataclasses import dataclass, field, replace

RU = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def slugify(text: str) -> str:
    """Транслит + дефисы, ≤40 символов — для имени MD-файла."""
    low = "".join(RU.get(ch, ch) for ch in text.lower().strip())
    kept = "".join(ch if (ch.isascii() and (ch.isalnum() or ch == "-")) else "-" for ch in low)
    while "--" in kept:
        kept = kept.replace("--", "-")
    return kept.strip("-")[:40]


@dataclass(frozen=True, slots=True)
class Concept:
    """Понятие: термин → определение."""

    term: str
    definition: str


@dataclass(frozen=True, slots=True)
class PracticeStep:
    """Шаг практики: машина, команда, объяснение, результат; verify/cleanup — для runbook."""

    machine: str
    command: str
    explanation: str
    result: str | None = None
    verify: str | None = None
    cleanup: str | None = None


@dataclass(frozen=True, slots=True)
class BlockSource:
    """Ссылка блока на источник (uid) и главу."""

    source: str
    chapter: int | None = None
    title: str = ""


@dataclass(frozen=True, slots=True)
class BlockDraft:
    """Черновик блока знаний, из которого собирается MD-файл."""

    title: str
    summary: str = ""
    kind: str = "lesson"  # lesson | note | runbook
    concepts: tuple[Concept, ...] = ()
    theses: tuple[str, ...] = ()
    my_examples: tuple[str, ...] = ()
    mermaid: str | None = None
    practice: tuple[PracticeStep, ...] = ()
    weak_spots: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    category_suggestion: str | None = None
    sources: tuple[BlockSource, ...] = ()

    def weak_spots_count(self) -> int:
        return len(self.weak_spots)


@dataclass(frozen=True, slots=True)
class BlockMeta:
    """Метаданные блока из frontmatter/индекса (без тела)."""

    uid: str
    title: str
    kind: str = "lesson"
    summary: str = ""
    category_path: str | None = None
    category_status: str = "suggested"
    tags: tuple[str, ...] = ()
    sources: tuple[BlockSource, ...] = ()
    session_uid: str | None = None
    conversation_uid: str | None = None
    activity_uid: str | None = None
    version: int = 1
    created: str = ""
    updated: str = ""
    links: tuple[str, ...] = ()
    weak_spots_count: int = 0
    path: str = ""
    versions_count: int = 0
    back_links: tuple[str, ...] = ()
    verified: bool = False  # «проговорённое» знание: блок из сессии, не конспект (R-18)


@dataclass(frozen=True, slots=True)
class Block:
    """Блок целиком: метаданные + MD-тело."""

    meta: BlockMeta
    content: str = ""

    def with_meta(self, meta: BlockMeta) -> "Block":
        """Копия блока с новыми метаданными (тело то же)."""
        return Block(meta=meta, content=self.content)

    def next_version(self) -> "Block":
        """Блок с версией+1 (используется перед записью правки)."""
        return self.with_meta(replace(self.meta, version=self.meta.version + 1))


def apply_patch(draft: BlockDraft, patch: dict) -> BlockDraft:
    """Применить частичный патч к драфту: списки заменяются целиком, кроме append_*-операций.

    Raises:
        ValueError: неизвестное поле патча.
    """
    allowed = set(BlockDraft.__dataclass_fields__)
    appends = {
        "append_theses": "theses",
        "append_examples": "my_examples",
        "append_concepts": "concepts",
        "append_weak_spots": "weak_spots",
    }
    # последовательные поля: патч приходит списком, в драфте храним tuple
    seq_fields = {"theses", "my_examples", "weak_spots", "open_questions", "links", "tags"}
    changes: dict = {}
    for key, value in patch.items():
        if key in appends:
            field_name = appends[key]
            if field_name == "concepts":
                extra = tuple(Concept(**c) for c in value)
            else:
                extra = tuple(value)
            changes[field_name] = getattr(draft, field_name) + extra
        elif key in allowed:
            if key == "concepts" and value:
                changes[key] = tuple(Concept(**c) for c in value)
            elif key == "practice" and value:
                changes[key] = tuple(PracticeStep(**p) for p in value)
            elif key == "sources" and value:
                changes[key] = tuple(BlockSource(**s) for s in value)
            elif key in {"concepts", "practice", "sources"}:
                changes[key] = ()
            elif key in seq_fields and isinstance(value, list):
                changes[key] = tuple(value)
            else:
                changes[key] = value
        else:
            raise ValueError(f"неизвестное поле патча: {key}")
    return replace(draft, **changes)


# --- Сборка MD из драфта ---


def draft_to_markdown(uid: str, draft: BlockDraft, meta_extra: dict) -> str:
    """Собрать MD-файл v2: frontmatter (YAML-словарь) + секции в фиксированном порядке.

    category_status и review берутся из meta_extra (при правке — из текущего файла,
    чтобы подтверждённая категория и SRS-состояние не сбрасывались при пересборке).
    """
    import yaml

    frontmatter: dict = {
        "id": uid,
        "kind": draft.kind,
        "title": draft.title,
        "summary": draft.summary,
        "category": draft.category_suggestion,
        "category_status": meta_extra.get("category_status", "suggested"),
        "tags": list(draft.tags),
        "sources": [{"source": s.source, "chapter": s.chapter, "title": s.title} for s in draft.sources],
        "session": meta_extra.get("session_uid"),
        "conversation": meta_extra.get("conversation_uid"),
        "activity": meta_extra.get("activity_uid"),
        "created": meta_extra.get("created", ""),
        "updated": meta_extra.get("updated", ""),
        "version": meta_extra.get("version", 1),
        "verified": bool(meta_extra.get("verified", False)),
        "review": meta_extra.get("review") or {"ease": 2.5, "interval": 1, "due": None},
    }
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()

    parts = [f"---\n{fm}\n---\n", f"# {draft.title}\n"]
    if draft.summary:
        parts.append(f"> {draft.summary}\n")

    def section(title: str, lines: list[str]) -> None:
        if not lines:
            return
        parts.append(f"\n## {title}\n")
        parts.extend(lines)

    section("Ключевые понятия", [f"- **{c.term}** — {c.definition}" for c in draft.concepts])
    section("Тезисы", [f"- {t}" for t in draft.theses])
    section("Как я это понял", [f"- «{e}»" for e in draft.my_examples])
    if draft.mermaid:
        parts.append(f"\n## Схема\n\n```mermaid\n{sanitize_mermaid(draft.mermaid.strip())}\n```\n")
    section(
        "Практика",
        [
            f"{i}. **{p.machine}** · `{p.command}` — {p.explanation}"
            + (f"; результат: {p.result}" if p.result else "")
            + (f"; проверка: {p.verify}" if p.verify else "")
            + (f"; откат: {p.cleanup}" if p.cleanup else "")
            for i, p in enumerate(draft.practice, 1)
        ],
    )
    # между callout'ами пустая строка — иначе парсер (и рендереры) склеивают их в один
    section("Дозакрепить", [f"> [!WARNING]\n> {w}\n" for w in draft.weak_spots])
    section("Вопросы на потом", [f"- {q}" for q in draft.open_questions])
    section("Связи", [f"- [[{link}]]" for link in draft.links])
    section(
        "Источники",
        [
            f"- {s.title or s.source} (`{s.source}#{s.chapter}`)"
            if s.chapter
            else f"- {s.title or s.source} (`{s.source}`)"
            for s in draft.sources
        ],
    )
    return "\n".join(parts)


WIKILINK = re.compile(r"\[\[(blk_[0-9a-f]+)\]\]")


def parse_markdown(content: str) -> tuple[dict, str]:
    """Разобрать MD-файл: frontmatter (dict) + тело.

    Raises:
        ValueError: нет корректного frontmatter.
    """
    import yaml

    if not content.startswith("---"):
        raise ValueError("MD-файл не начинается с frontmatter")
    _, fm_raw, body = content.split("---", 2)
    meta = yaml.safe_load(fm_raw) or {}
    return meta, body.lstrip("\n")


MERMAID_UNSAFE = re.compile(
    "[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u2b00-\u2bff\u2190-\u21ff\u2700-\u27bf]"
)


def sanitize_mermaid(code: str) -> str:
    """Убрать символы, ломающие парсер mermaid (эмодзи, пиктограммы, текстовые стрелки)."""
    return MERMAID_UNSAFE.sub("", code)


def count_weak_spots(body: str) -> int:
    """Число пунктов «Дозакрепить» в теле блока (callout-строки)."""
    import re

    m = re.search(r"^## Дозакрепить\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not m:
        return 0
    return sum(1 for line in m.group(1).splitlines() if line.strip().startswith("> [!WARNING]"))


def extract_links(body: str) -> tuple[str, ...]:
    """Все [[blk_…]] из тела."""
    return tuple(WIKILINK.findall(body))


def plain_text(body: str) -> str:
    """Тело без разметки — для FTS."""
    text = re.sub(r"```.*?```", " ", body, flags=re.S)
    text = re.sub(r"[#>*`|\[\]()-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True, slots=True)
class Category:
    """Узел дерева категорий."""

    path: str
    title: str
    parent_path: str | None = None
    color: str | None = None
    icon: str | None = None
    sort: int = 0
    children: tuple["Category", ...] = field(default_factory=tuple)


def default_categories() -> list[Category]:
    """Стартовое дерево из ТЗ (programming/infra/life)."""
    return [
        Category(path="programming", title="Программирование", color="sky", icon="code"),
        Category(path="programming/python", title="Python", color="sky", icon="code"),
        Category(path="programming/python/oop", title="ООП", color="sky", icon="code"),
        Category(path="infra", title="Инфраструктура", color="emerald", icon="server"),
        Category(path="infra/kubernetes", title="Kubernetes", color="emerald", icon="server"),
        Category(path="life", title="Личное", color="amber", icon="heart"),
        Category(path="life/cooking", title="Кулинария", color="amber", icon="chef-hat"),
    ]


def normalize_category_path(path: str) -> str:
    """Нормализовать путь: нижний регистр, без лишних слэшей."""
    return "/".join(p.strip().lower() for p in path.split("/") if p.strip())


def category_ancestors(path: str) -> list[str]:
    """Пути всех предков (включая сам путь)."""
    parts = path.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def with_ancestors(path: str) -> list[str]:
    """Путь и все его префиксы."""
    parts = path.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def writer_out_to_draft(out, kind: str) -> BlockDraft:
    """Выход block_writer (pydantic) → доменный BlockDraft."""
    from .domain import BlockSource, Concept, PracticeStep

    return BlockDraft(
        title=out.title,
        summary=out.summary,
        kind=kind if kind in {"lesson", "note", "runbook"} else "lesson",
        concepts=tuple(Concept(c.term, c.definition) for c in out.concepts),
        theses=tuple(out.theses),
        my_examples=tuple(out.my_examples),
        mermaid=out.mermaid,
        practice=tuple(PracticeStep(p.machine, p.command, p.explanation, p.result) for p in out.practice),
        weak_spots=tuple(out.weak_spots),
        open_questions=tuple(out.open_questions),
        links=tuple(link for link in out.links if link.startswith("blk_")),
        tags=tuple(out.tags),
        category_suggestion=out.category_suggestion,
        # источник — только реальный uid (модель любит подставить заголовок)
        sources=tuple(
            BlockSource(source=s.source, chapter=s.chapter, title=s.title)
            for s in getattr(out, "sources", []) or []
            if str(s.source).startswith("src_")
        ),
    )


def dict_of_meta(meta: BlockMeta) -> dict:
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
        "verified": meta.verified,
    }


def assemble_frontmatter(meta_raw: dict, body: str) -> str:
    """Склеить frontmatter + тело обратно в MD."""
    import yaml

    fm = yaml.safe_dump(meta_raw, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body}"
