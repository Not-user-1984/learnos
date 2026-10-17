import re
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


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "-").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _page_paragraphs(page: fitz.Page) -> list[str]:
    """Абзацы страницы: каждый блок PDF — абзац, строки блока склеиваются пробелом."""
    paragraphs = []
    for block in page.get_text("blocks"):
        block_text = block[4] if len(block) > 4 else ""
        if not block_text:
            continue
        lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_NOISE.match(ln) for ln in lines):
            continue
        paragraphs.append(" ".join(lines))
    return paragraphs


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

        top = [(title, page) for level, title, page in toc if level == 1]
        if not top:
            top = [(title, page) for level, title, page in toc]

        out_dir = DATA_DIR / "sources" / str(source_id) / "chapters"
        out_dir.mkdir(parents=True, exist_ok=True)

        chapters = []
        for idx, (title, start_page) in enumerate(top, start=1):
            end_page = top[idx][1] if idx < len(top) else doc.page_count + 1
            pages = range(start_page - 1, min(end_page - 1, doc.page_count))
            paragraphs: list[str] = []
            for p in pages:
                page_paras = _page_paragraphs(doc.load_page(p))
                if not paragraphs or not page_paras:
                    paragraphs.extend(page_paras)
                    continue
                # абзац, продолжающийся через страницу: без точки в конце — приклеиваем
                if not paragraphs[-1].endswith((".", "!", "?", ":", "»", '"')):
                    paragraphs[-1] = f"{paragraphs[-1]} {page_paras[0]}"
                    paragraphs.extend(page_paras[1:])
                else:
                    paragraphs.extend(page_paras)
            # дублированный заголовок главы в начале текста (из TOC и из тела страницы)
            if paragraphs and paragraphs[0].strip().lower().strip(". :") == title.strip().lower():
                paragraphs = paragraphs[1:]
            text = _clean("\n\n".join(paragraphs))
            chapter_path = out_dir / f"ch_{idx:02d}.md"
            chapter_path.write_text(f"# {title}\n\n{text}\n", encoding="utf-8")

            summary = text[:280] + ("…" if len(text) > 280 else "")
            conn.execute(
                "INSERT INTO chapters(source_id, idx, title, path, tokens_est, summary) VALUES (?,?,?,?,?,?)",
                (source_id, idx, title, str(chapter_path), max(1, len(text) // 4), summary),
            )
            chapters.append(
                {
                    "idx": idx,
                    "title": title,
                    "pages": f"{start_page}-{end_page - 1}",
                    "tokens_est": len(text) // 4,
                }
            )

        conn.execute("UPDATE sources SET status = 'processed' WHERE id = ?", (source_id,))
        conn.commit()
        return {
            "ok": True,
            "source_id": source_id,
            "title": src["title"],
            "pages": doc.page_count,
            "chapters": chapters,
            "dir": str(out_dir),
        }
    finally:
        conn.close()
