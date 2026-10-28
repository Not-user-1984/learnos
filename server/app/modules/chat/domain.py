"""Домен чата: претрекер контента — распознаёт ссылки/ID в сообщении без LLM (T-036).

Претрекер только добавляет контекст агенту (заметка в system_extra), текст
сообщения не меняется и не режется.
"""

import re
from dataclasses import dataclass

# YouTube: полный URL (watch/shorts/live) или короткий youtu.be
_YOUTUBE_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtu\.be/[\w-]{11,}"
    r"|youtube\.com/(?:watch\?\S*?v=[\w-]{11,}|shorts/[\w-]{11,}|live/[\w-]{11,}))"
)
# arXiv: только с явным префиксом — «голый» 2401.12345 неотличим от номера версии/даты
_ARXIV_RE = re.compile(
    r"arxiv:\s*(\d{4}\.\d{4,5})(?:v\d+)?|arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+")
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


@dataclass(frozen=True, slots=True)
class ContentSignal:
    """Распознанный контент: тип, точное значение и подсказка действий агенту."""

    kind: str  # youtube | url | arxiv | doi
    value: str
    hint: str


def detect_content(text: str) -> list[ContentSignal]:
    """Найти контент в тексте сообщения: YouTube, arXiv, DOI, произвольные URL.

    Порядок проверки от конкретного к общему; уже занятые совпадения (например
    ссылка YouTube или arxiv.org) в общем URL-списке не дублируются.
    """
    signals: list[ContentSignal] = []
    taken: list[tuple[int, int]] = []  # spans, занятые более specific-матчами

    def take(m: re.Match, kind: str, value: str) -> None:
        taken.append(m.span())
        signals.append(ContentSignal(kind, value, _HINTS[kind](value)))

    for m in _YOUTUBE_RE.finditer(text):
        take(m, "youtube", m.group(0))
    for m in _ARXIV_RE.finditer(text):
        aid = m.group(1) or m.group(2)
        take(m, "arxiv", f"arXiv:{aid}")
    for m in _DOI_RE.finditer(text):
        take(m, "doi", m.group(0).rstrip(".,;:!?"))
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:!?)]}")
        if any(start < m.end() and end > m.start() for start, end in taken):
            continue
        take(m, "url", url)
    return _dedup(signals)


def content_note(text: str) -> str:
    """Заметка в system_extra агента о распознанном контенте ('' — контента нет)."""
    signals = detect_content(text)
    if not signals:
        return ""
    return "Распознан контент в сообщении пользователя:\n" + "\n".join(f"- {s.hint}" for s in signals)


def _hint_youtube(url: str) -> str:
    return (
        f"В сообщении YouTube-ссылка {url}. Доступные действия: "
        f"add_source(kind=video, url={url}) → process_source — добавит видео в Библиотеку с транскриптом."
    )


def _hint_arxiv(value: str) -> str:
    aid = value.removeprefix("arXiv:")
    return (
        f"В сообщении научная работа {value}. Доступные действия: "
        f"academic_search(query='{value}') — метаданные и похожие работы; "
        f"web_read(url='https://arxiv.org/abs/{aid}') — прочитать аннотацию."
    )


def _hint_doi(doi: str) -> str:
    return (
        f"В сообщении DOI {doi}. Доступные действия: academic_search(query='{doi}') — найти работу; "
        "web_read — страница издателя по ссылке из результатов."
    )


def _hint_url(url: str) -> str:
    return (
        f"В сообщении веб-ссылка {url}. Доступные действия: web_read(url={url}) — прочитать статью "
        f"порционно; add_source(kind=web, url={url}) → process_source — добавить в Библиотеку."
    )


_HINTS = {
    "youtube": _hint_youtube,
    "arxiv": _hint_arxiv,
    "doi": _hint_doi,
    "url": _hint_url,
}


def _dedup(signals: list[ContentSignal]) -> list[ContentSignal]:
    """Одна ссылка дважды в сообщении — один сигнал."""
    seen: set[tuple[str, str]] = set()
    out = []
    for s in signals:
        if (s.kind, s.value) not in seen:
            seen.add((s.kind, s.value))
            out.append(s)
    return out
