import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz

from app.db import get_db
from app.paths import DATA_DIR

# колонтитулы и служебные строки, которые не несут текста главы
_NOISE = re.compile(
    r"^(глава\s+\d+|chapter\s+\d+|предисловие|preface|оглавление|содержание|contents|\d+)$", re.I
)

# минимальные размеры картинки (pt): ниже — декоративные элементы вёрстки
_MIN_IMAGE_PT = 40.0
_RENDER_DPI = 150


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "-").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _block_text(block: dict) -> str:
    """Текст блока: строки из спанов склеиваются, строки блока — через \\n."""
    lines = []
    for line in block.get("lines", []):
        parts = "".join(span.get("text", "") for span in line.get("spans", []))
        if parts.strip():
            lines.append(parts.strip())
    return "\n".join(lines)


def _text_paragraph(block_text: str) -> str | None:
    """Блок PDF → абзац (строки пробелом); чистый шум отбрасывается."""
    if not block_text:
        return None
    lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
    if not lines or all(_NOISE.match(ln) for ln in lines):
        return None
    return " ".join(lines)


class _PageRenderer:
    """Куски страницы в порядке вёрстки: абзацы текста и картинки (PNG на диск)."""

    def __init__(self, source_uid: str, images_dir: Path) -> None:
        self._uid = source_uid
        self._dir = images_dir

    def pieces(self, page: fitz.Page) -> list[tuple[str, str]]:
        """[("p", абзац), ("img", markdown-ссылка)] в порядке блоков страницы."""
        out: list[tuple[str, str]] = []
        page_images = 0
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") == 1:
                md = self._image_md(page, block, page_images)
                if md:
                    page_images += 1
                    out.append(("img", md))
                continue
            paragraph = _text_paragraph(_block_text(block))
            if paragraph:
                out.append(("p", paragraph))
        return out

    def _image_md(self, page: fitz.Page, block: dict, n: int) -> str | None:
        """Рендер image-блока по bbox → PNG в images/, markdown-ссылка на эндпоинт."""
        x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
        if y1 - y0 < _MIN_IMAGE_PT or x1 - x0 < _MIN_IMAGE_PT:
            return None  # декоративная мелочь (линейки, маркеры)
        if not block.get("width") or not block.get("height"):
            return None  # пустой image-блок без растра
        name = f"img_p{page.number + 1}_{n}.png"
        try:
            pix = page.get_pixmap(clip=fitz.Rect(x0, y0, x1, y1), dpi=_RENDER_DPI)
            pix.save(self._dir / name)
        except Exception:  # noqa: BLE001 — битая картинка не роняет главу
            return None
        return f"![рисунок](/api/sources/{self._uid}/images/{name})"


def _sections_for(toc: list[tuple[int, str, int]], start: int, end: int, level: int = 2) -> str:
    """Секции уровня ниже глав внутри диапазона: [{"title", "page"}] JSON-ом."""
    sections = [{"title": t, "page": p} for lvl, t, p in toc if lvl == level and start <= p < end]
    return json.dumps(sections, ensure_ascii=False)


# часть-подобные закладки level-1: главы прячутся уровнем ниже
_PART_RE = re.compile(r"^(часть|part|book|том)\b", re.I)

# буквы для определения языка (нижний регистр)
_CYR_RE = re.compile(r"[а-яё]")
_LAT_RE = re.compile(r"[a-z]")


def detect_language(text: str, min_letters: int = 200) -> str | None:
    """ru/en по доле кириллицы среди букв: русский технический текст содержит
    английские термины, поэтому порог ru невысокий. Мало букв — не определяем."""
    sample = text.lower()
    cyr = len(_CYR_RE.findall(sample))
    lat = len(_LAT_RE.findall(sample))
    if cyr + lat < min_letters:
        return None
    return "ru" if cyr / (cyr + lat) >= 0.3 else "en"


def _top_entries(toc: list[tuple[int, str, int]]) -> tuple[list[tuple[str, int]], int]:
    """Записи-кандидаты в главы и уровень секций.

    Обычная книга: level-1 → главы, level-2 → секции. Книга с частями
    («Часть I. …» в level-1, главы в level-2): главами становятся level-2
    внутри частей (плюс не-частные level-1 вроде предисловия — куратор их
    вычистит), секции — level-3.
    """
    top1 = [(t, p) for lvl, t, p in toc if lvl == 1]
    if not top1:
        return [(t, p) for _lvl, t, p in toc], 0  # без level-1: все уровни, секции не строим
    parts = [(t, p) for t, p in top1 if _PART_RE.match(t.strip())]
    if parts:
        spans = [(p, (parts[i + 1][1] if i + 1 < len(parts) else 10**9)) for i, (_, p) in enumerate(parts)]
        inside = [(t, p) for lvl, t, p in toc if lvl == 2 and any(s <= p < e for s, e in spans)]
        if len(inside) >= 3:
            rest = [(t, p) for t, p in top1 if not _PART_RE.match(t.strip())]
            return sorted(rest + inside, key=lambda tp: tp[1]), 3
    return top1, 2


def main(source_id: int) -> dict:
    conn = get_db()
    try:
        src = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not src:
            return {"error": f"source {source_id} not found"}
        pdf_path = src["local_path"]
        if not pdf_path or not Path(pdf_path).exists():
            return {"error": f"local_path not set or missing: {pdf_path}"}

        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        if not toc:
            return {
                "error": "PDF без закладок (TOC) — эвристика по заголовкам пока не реализована",
                "hint": "конвертировать с закладками или добавить TOC",
            }

        top, section_level = _top_entries(toc)
        if section_level == 0:
            toc = []  # уровни перемешаны — секции не строим

        src_dir = DATA_DIR / "sources" / str(source_id)
        out_dir = src_dir / "chapters"
        images_dir = src_dir / "images"
        # переобработка: старые главы и картинки недействительны
        for d in (out_dir, images_dir):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        renderer = _PageRenderer(src["uid"], images_dir)

        chapters = []
        entries = []  # вход куратора структуры: все top-записи закладок как есть
        chapter_texts: list[str] = []  # для определения языка книги
        for idx, (title, start_page) in enumerate(top, start=1):
            end_page = top[idx][1] if idx < len(top) else doc.page_count + 1
            pages = range(start_page - 1, min(end_page - 1, doc.page_count))
            pieces: list[tuple[str, str]] = []
            for p in pages:
                page_pieces = renderer.pieces(doc.load_page(p))
                if not pieces or not page_pieces:
                    pieces.extend(page_pieces)
                    continue
                # абзац, продолжающийся через страницу: без точки в конце — приклеиваем
                if (
                    pieces[-1][0] == "p"
                    and page_pieces[0][0] == "p"
                    and not pieces[-1][1].endswith((".", "!", "?", ":", "»", '"'))
                ):
                    pieces[-1] = ("p", f"{pieces[-1][1]} {page_pieces[0][1]}")
                    pieces.extend(page_pieces[1:])
                else:
                    pieces.extend(page_pieces)
            paragraphs = [text for kind, text in pieces if kind == "p"]
            # дублированный заголовок главы в начале текста (из TOC и из тела страницы)
            if paragraphs and paragraphs[0].strip().lower().strip(". :") == title.strip().lower():
                paragraphs = paragraphs[1:]
            text_items = [text if kind == "p" else "\n\n" + text + "\n\n" for kind, text in pieces]
            if text_items and text_items[0].startswith("\n\n"):
                text_items[0] = text_items[0][2:]
            text = _clean("".join(text_items))
            chapter_texts.append(text)
            chapter_path = out_dir / f"ch_{idx:02d}.md"
            chapter_path.write_text(f"# {title}\n\n{text}\n", encoding="utf-8")

            snippet = " ".join(paragraphs[:3])[:240]
            summary = text[:280] + ("…" if len(text) > 280 else "")
            sections_json = _sections_for(toc, start_page, end_page, section_level)
            conn.execute(
                "INSERT INTO chapters(source_id, idx, title, path, tokens_est, summary,"
                " start_page, end_page, sections_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    source_id,
                    idx,
                    title,
                    str(chapter_path),
                    max(1, len(text) // 4),
                    summary,
                    start_page,
                    end_page - 1,
                    sections_json,
                ),
            )
            chapters.append(
                {
                    "idx": idx,
                    "title": title,
                    "pages": f"{start_page}-{end_page - 1}",
                    "tokens_est": len(text) // 4,
                }
            )
            entries.append(
                {
                    "idx": idx,
                    "title": title,
                    "start_page": start_page,
                    "page_count": max(0, end_page - start_page),
                    "snippet": snippet,
                }
            )

        # язык книги: сэмпл из середины первых глав (без титула/оглавления достаточно букв)
        lang = detect_language("\n".join(chapter_texts[:5]))
        meta = json.loads(src["meta_json"] or "{}")
        if lang:
            meta["lang"] = lang
        conn.execute(
            "UPDATE sources SET status = 'processed', meta_json = ? WHERE id = ?",
            (json.dumps(meta, ensure_ascii=False), source_id),
        )
        conn.commit()
        return {
            "ok": True,
            "source_id": source_id,
            "uid": src["uid"],
            "title": src["title"],
            "lang": lang,
            "pages": doc.page_count,
            "chapters": chapters,
            "entries": entries,
            "dir": str(out_dir),
        }
    finally:
        conn.close()
