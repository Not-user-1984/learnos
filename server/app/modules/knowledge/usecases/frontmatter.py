"""Разбор frontmatter+тела блока в BlockDraft (B-009: вынесено из service)."""

from ..domain import BlockDraft, Concept, PracticeStep


def draft_from_frontmatter(meta_raw: dict, content: str) -> BlockDraft:
    """Разобрать текущий MD обратно в драфт (для патчей) — без потерь секций.

    Парсеры зеркальны рендеру draft_to_markdown: concepts/practice/weak_spots
    восстанавливаются полностью, иначе любая правка блока стирала бы их.
    """
    from ..domain import BlockSource

    body = content.split("---", 2)[-1]
    theses = _section_items(body, "Тезисы")
    examples = [x.strip("«» ") for x in _section_items(body, "Как я это понял")]
    weak = _weak_spots(body)
    mermaid = None
    if "```mermaid\n" in body:
        mermaid = body.split("```mermaid\n", 1)[1].split("\n```", 1)[0]
    links = tuple(meta_raw.get("links") or ()) or tuple(
        lk for lk in _section_items(body, "Связи") if lk.startswith("[[") and lk.endswith("]]")
    )
    return BlockDraft(
        title=meta_raw.get("title", "Без названия"),
        summary=meta_raw.get("summary") or "",
        kind=meta_raw.get("kind", "lesson"),
        concepts=tuple(_concepts(body)),
        theses=tuple(theses),
        my_examples=tuple(examples),
        mermaid=mermaid,
        practice=tuple(_practice(body)),
        weak_spots=tuple(w for w in weak if w),
        open_questions=tuple(_section_items(body, "Вопросы на потом")),
        links=tuple(lk[2:-2] if lk.startswith("[[") else lk for lk in links),
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


def _weak_spots(body: str) -> list[str]:
    """Пункты «Дозакрепить»: каждый callout — блок от маркера «> [!WARNING]» до пустой строки.

    Понимает и старый слитный формат (callout'ы без пустой строки между ними) —
    маркер начинает новый пункт.
    """
    import re

    m = re.search(r"^## Дозакрепить\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not m:
        return []
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            text = " ".join(buf).strip()
            if text and text != "[!WARNING]":
                out.append(text)
        buf.clear()

    for raw in m.group(1).splitlines():
        line = raw.strip()
        if line.startswith("> [!WARNING]"):
            flush()
        elif line.startswith(">"):
            buf.append(line.lstrip("> ").strip())
        elif line == "":
            flush()
        elif buf:
            buf.append(line)
    flush()
    return out


def _concepts(body: str) -> list:
    """Понятия из «Ключевые понятия»: строки «- **термин** — определение»."""
    import re

    out = []
    for line in _section_items(body, "Ключевые понятия"):
        m = re.match(r"^\*\*(.+?)\*\* — (.*)$", line)
        if m:
            out.append(Concept(term=m.group(1).strip(), definition=m.group(2).strip()))
    return out


def _practice(body: str) -> list:
    """Шаги из «Практика»: «N. **машина** · `команда` — пояснение; результат: …; проверка: …»."""
    import re

    out = []
    for line in _section_items(body, "Практика"):
        m = re.match(r"^\d+\.\s+\*\*(.+?)\*\* · `(.+?)` — (.*)$", line)
        if not m:
            continue
        machine, command, rest = m.group(1).strip(), m.group(2), m.group(3)
        # split с захватом метки: [пояснение, 'результат', val, 'проверка', val, ...]
        chunks = re.split(r"; (результат|проверка|откат): ", rest)
        explanation = chunks[0].strip()
        extras = {"результат": None, "проверка": None, "откат": None}
        for i in range(1, len(chunks) - 1, 2):
            extras[chunks[i]] = chunks[i + 1].strip() or None
        out.append(
            PracticeStep(
                machine=machine,
                command=command,
                explanation=explanation,
                result=extras["результат"],
                verify=extras["проверка"],
                cleanup=extras["откат"],
            )
        )
    return out
