"""R-20: качество ингеста книг — код не схлопывается, переносы склеиваются, summary по всей главе."""

import importlib.util
import sys
from pathlib import Path

_SKILL = Path(__file__).resolve().parents[2] / "skills" / "book-splitter" / "run.py"


def _load_splitter():
    spec = importlib.util.spec_from_file_location("book_splitter_run", _SKILL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["book_splitter_run"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_mono_block_becomes_fenced_code():
    """Листинг кода — fenced-блок с сохранением строк, а не одна строка (R-20)."""
    mod = _load_splitter()
    block = {
        "lines": [
            {
                "spans": [
                    {"text": "kubectl get pods -A", "flags": 8},
                ]
            },
            {
                "spans": [
                    {"text": "  -o wide", "flags": 8},
                ]
            },
        ]
    }
    out = mod._mono_paragraph(block)  # noqa: SLF001
    assert out == "```\nkubectl get pods -A\n  -o wide\n```"


def test_mono_ratio_detects_code_blocks():
    mod = _load_splitter()
    code_block = {
        "lines": [
            {"spans": [{"text": "def main(): pass", "flags": 8}]},
            {"spans": [{"text": "print('hi')", "flags": 8}]},
        ]
    }
    text_block = {"lines": [{"spans": [{"text": "Обычный текст абзаца с рассуждением", "flags": 0}]}]}
    assert mod._mono_ratio(code_block) >= 0.6  # noqa: SLF001
    assert mod._mono_ratio(text_block) < 0.2  # noqa: SLF001


def test_hyphenation_joined_without_defis():
    """«про-» + «цесс» → «процесс»: переносы вёрстки не калечат слова (R-20)."""
    mod = _load_splitter()
    para = mod._text_paragraph("Контейнер запускает про-\nцесс в изоляции")  # noqa: SLF001
    assert "процесс" in para
    assert "про- Hess" not in para


def test_soft_hyphen_removed_not_dashed():
    """Мягкий перенос — невидимый, удаляется, а не становится дефисом (R-20)."""
    mod = _load_splitter()
    cleaned = mod._clean("слон\u00adство")  # noqa: SLF001
    assert cleaned == "слонство"


def test_summarize_long_chapter_map_reduce(container, fake_llm, tmp_path):
    """Длинная глава: summary по чанкам + объединяющий вызов, а не по первым 12k (R-20)."""
    import json

    from app.llm.providers.fake import FakeTurn

    chapter = tmp_path / "ch.md"
    chapter.write_text("т" * 30000, encoding="utf-8")  # ~4 чанка
    src = container.library.add_source("book", "Толстая книга")
    with container.uow() as uow:
        container.library._chapters.insert(  # noqa: SLF001
            uow.session,
            source_id=src["id"],
            idx=1,
            title="Глава",
            path=str(chapter),
        )

    def turn(marker: str) -> str:
        return json.dumps(
            {"summary": f"выжимка {marker}", "key_points": [marker], "has_exercises": False},
            ensure_ascii=False,
        )

    # 4 чанка + объединяющий вызов
    for i in range(1, 5):
        fake_llm.queue(FakeTurn(text=turn(f"ч{i}")))
    fake_llm.queue(FakeTurn(text=turn("итог")))

    job = {"id": 999, "kind": "summarize_chapters", "target": src["uid"], "total": 1}
    with container.uow() as uow:
        container.library._jobs.enqueue(  # noqa: SLF001
            uow.session,
            kind="summarize_chapters",
            target=src["uid"],
            total=1,
            now="2026-11-01T00:00:00",
        )
    out = container.library.run_job(job)
    assert out.get("ok") is True
    with container.uow() as uow:
        row = container.library._chapters.get(  # noqa: SLF001
            uow.session, src["id"], 1
        )
    assert row["summary"] == "выжимка итог"
