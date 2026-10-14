import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz

from app.db import get_db
from app.paths import DATA_DIR


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "-").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
            text = _clean("\n\n".join(doc.load_page(p).get_text("text") for p in pages))
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
