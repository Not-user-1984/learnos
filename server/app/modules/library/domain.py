"""Домен библиотеки: виды источников, статусы обработки, правила, структура книги."""

import re

SourceKind = str  # book | video | web

# класс записи TOC: содержательная глава / служебный мусор / приложение
EntryClass = str  # chapter | front_matter | appendix

# стоп-слова служебных страниц (тайтл нормализуется: lower, пробелы сжаты)
FRONT_MATTER_WORDS = (
    "оглавление",
    "содержание",
    "contents",
    "index",
    "указатель",
    "лицензия",
    "licence",
    "license",
    "посвящение",
    "dedication",
    "титул",
    "титульный лист",
    "cover",
    "обложка",
    "колофон",
    "copyright",
    "выходные данные",
    "благодарности",
    "acknowledgments",
    "acknowledgements",
    "об авторе",
    "about the author",
)

APPENDIX_WORDS = ("приложение", "appendix", "глоссарий", "glossary")

# предисловия-вводные: короткие (1–2 стр.) записи с такими названиями — служебные,
# даже если LLM-куратор решил оставить их главами («Введение» сюда НЕ входит)
PREFACE_WORDS = (
    "предисловие",
    "пролог",
    "вступление",
    "эпилог",
    "foreword",
    "preface",
    "prologue",
    "послесловие",
    "afterword",
)

# «Глава 3. X» / «Chapter 12: Y» / «3. Z» / «10 — T» в начале названия
_NUMBERED_TITLE = re.compile(
    r"^(?:глава|chapter|chap\.?|раздел)\s+(\d+)|^(\d{1,3})[.)\s\u2014\u2013:-]", re.I
)


class SourceRules:
    """Правила жизни источника."""

    @staticmethod
    def can_process(status: str) -> bool:
        """Обработку можно запускать из found/chosen/failed; повторную из processed — только с force."""
        return status in {"found", "chosen", "failed"}

    @staticmethod
    def normalize_kind(kind: str) -> str:
        """Привести kind к известному."""
        k = kind.strip().lower()
        if k in {"pdf", "книга", "book"}:
            return "book"
        if k in {"youtube", "video", "видео"}:
            return "video"
        if k in {"article", "web", "статья"}:
            return "web"
        raise ValueError(f"неизвестный вид источника: {kind}")


def parse_chapter_number(title: str) -> int | None:
    """Номер главы из её названия: «Глава 3. Ветвление» → 3, «10. Git изнутри» → 10, «Введение» → None."""
    m = _NUMBERED_TITLE.match(title.strip())
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def classify_toc_entry(title: str, page_count: int) -> EntryClass:
    """Эвристика-фолбэк куратора структуры (без LLM).

    front_matter — служебные страницы по стоп-словам и записи короче 3 страниц
    (кроме приложений: короткое приложение остаётся приложением).
    """
    t = re.sub(r"\s+", " ", title).strip().lower()
    if t.startswith(APPENDIX_WORDS):
        return "appendix"
    if any(w in t for w in FRONT_MATTER_WORDS):
        return "front_matter"
    if page_count < 3:
        return "front_matter"
    return "chapter"


def merge_curator_labels(
    entries: list[dict], heuristic: dict[int, EntryClass], llm: dict[int, EntryClass] | None
) -> dict[int, EntryClass]:
    """Финальные классы: LLM + жёсткие правила эвристики поверх.

    LLM понимает контекст лучше стоп-слов, но иногда тащит короткие предисловия
    в главы. Правила эвристики, которые нельзя обойти: стоп-слова (оглавление,
    лицензия, титул…) и короткие (1–2 стр.) предисловия/прологи/вступления —
    всегда front_matter; длинное «Введение» остаётся главой.
    """
    out: dict[int, EntryClass] = {}
    for e in entries:
        idx, title = e["idx"], e["title"]
        pages = int(e.get("page_count") or 0)
        h = heuristic.get(idx, "chapter")
        t = re.sub(r"\s+", " ", title).strip().lower()
        hard_front = any(w in t for w in FRONT_MATTER_WORDS) or (pages < 3 and t.startswith(PREFACE_WORDS))
        if hard_front:
            out[idx] = "front_matter"
            continue
        out[idx] = llm.get(idx, h) if llm is not None else h
    return out
