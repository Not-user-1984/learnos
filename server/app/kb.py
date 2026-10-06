from .paths import KB_DIR
from .util import new_uid

RU = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    return "".join(RU.get(c, c) for c in text)


def slugify(text: str) -> str:
    low = translit(text.lower().strip())
    kept = [c if (c.isascii() and (c.isalnum() or c == "-")) else "-" for c in low]
    out = "".join(kept)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:40]


def write_block(course_id: int, draft: dict) -> tuple[str, str]:
    block_uid = draft.get("id") or new_uid("blk")
    title = draft.get("title", "Без названия")
    tags = draft.get("tags", [])
    sources = draft.get("sources", [])
    theses = draft.get("theses", [])
    examples = draft.get("my_examples", [])
    mermaid = draft.get("mermaid", "").strip()
    links = draft.get("links", [])

    fm = "---\n"
    fm += f"id: {block_uid}\n"
    fm += f"course: {course_id}\n"
    fm += f"title: {title}\n"
    fm += "tags: [" + ", ".join(str(t) for t in tags) + "]\n"
    fm += "sources: [" + ", ".join(str(s) for s in sources) + "]\n"
    fm += "review: {ease: 2.5, interval: 1, due: null}\n"
    fm += "---\n"

    parts = [fm, f"# {title}\n", "## Тезисы\n"]
    parts += [f"- {t}" for t in theses]
    parts.append("\n## Как я это понял\n")
    parts += [f"- {e}" for e in examples]
    if mermaid:
        parts.append("\n## Схема\n\n```mermaid\n" + mermaid + "\n```\n")
    if links:
        parts.append("\n## Связи\n")
        parts += [f"- [[{l}]]" for l in links]

    name = f"{block_uid}"
    slugged = slugify(title)
    if slugged:
        name = f"{block_uid}_{slugged}"
    path = KB_DIR / f"{name}.md"
    path.write_text("\n".join(parts), encoding="utf-8")
    return block_uid, str(path)


def read_block(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()
