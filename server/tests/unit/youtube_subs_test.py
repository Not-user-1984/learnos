"""youtube-to-summary: приоритет оригинальных дорожек (xx-orig), --ignore-errors, честный 429 (B-001)."""

import importlib.util
import sys
import types
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "youtube-to-summary"
VIDEO_ID = "abc12345678"


def _load_run():
    """run.py скилла с фейковым app.paths — без создания реальных каталогов данных."""
    fake_paths = types.ModuleType("app.paths")
    fake_paths.DATA_DIR = Path("/nonexistent")
    sys.modules["app.paths"] = fake_paths
    try:
        spec = importlib.util.spec_from_file_location("yt_summary_run", SKILL_DIR / "run.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.modules.pop("app.paths", None)
    return mod


run = _load_run()


def _proc(stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)


def _write_sub(data_dir: Path, name: str) -> Path:
    p = data_dir / "youtube" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello world\n", encoding="utf-8")
    return p


# ── _pick_sub: оригиналы приоритетнее переводов ──────────────────────


def test_pick_sub_prefers_orig_over_plain_langs():
    paths = [
        Path(f"{VIDEO_ID}.ru.vtt"),
        Path(f"{VIDEO_ID}.en.vtt"),
        Path(f"{VIDEO_ID}.en-orig.vtt"),
    ]
    assert run._pick_sub(paths) == Path(f"{VIDEO_ID}.en-orig.vtt")


def test_pick_sub_ru_orig_beats_en_orig():
    paths = [Path(f"{VIDEO_ID}.en-orig.vtt"), Path(f"{VIDEO_ID}.ru-orig.srt")]
    assert run._pick_sub(paths) == Path(f"{VIDEO_ID}.ru-orig.srt")


def test_pick_sub_without_orig_takes_ru():
    paths = [Path(f"{VIDEO_ID}.en.vtt"), Path(f"{VIDEO_ID}.ru.vtt")]
    assert run._pick_sub(paths) == Path(f"{VIDEO_ID}.ru.vtt")


def test_pick_sub_empty_returns_none():
    assert run._pick_sub([]) is None


# ── main(): команда yt-dlp и выбор файла ─────────────────────────────


def test_main_uses_orig_langs_and_ignore_errors(tmp_path, monkeypatch):
    captured: dict[str, list] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        _write_sub(tmp_path, f"{VIDEO_ID}.en-orig.vtt")
        return _proc(stdout=f"{VIDEO_ID}|Title")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)
    result = run.main(f"https://www.youtube.com/watch?v={VIDEO_ID}")

    assert result["ok"] is True
    cmd = captured["cmd"]
    assert "--ignore-errors" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "ru-orig,en-orig,ru,en"
    assert result["lang"] == "en"  # en-orig → en


def test_main_strips_orig_suffix_from_ru_lang(tmp_path, monkeypatch):
    """ru-orig → lang 'ru' (в мете источника — язык видео, не служебный суффикс)."""

    def fake_run(cmd, **kwargs):
        _write_sub(tmp_path, f"{VIDEO_ID}.ru-orig.vtt")
        return _proc(stdout=f"{VIDEO_ID}|Тайтл")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)
    result = run.main(f"https://youtu.be/{VIDEO_ID}")
    assert result["ok"] is True
    assert result["lang"] == "ru"


def test_main_removes_stale_sub_files_before_run(tmp_path, monkeypatch):
    """Частичные файлы прошлой попытки не должны попасть в выбор дорожки."""
    stale = _write_sub(tmp_path, f"{VIDEO_ID}.ru.vtt")

    def fake_run(cmd, **kwargs):
        return _proc(stdout=f"{VIDEO_ID}|Title")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)
    result = run.main(f"https://youtu.be/{VIDEO_ID}")

    assert not stale.exists()
    assert "субтитры не найдены" in result["error"]


# ── ошибки без файлов: 429 честно, хвост stderr попадает в текст ─────


def test_no_files_with_429_reports_rate_limit(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        return _proc(
            stdout=f"{VIDEO_ID}|T",
            stderr="ERROR: Unable to download video subtitles: HTTP Error 429: Too Many Requests",
        )

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)
    result = run.main(f"https://youtu.be/{VIDEO_ID}")

    assert "429" in result["error"]
    assert "повторите позже" in result["error"]
    assert "HTTP Error 429" in result["error"]  # хвост stderr — в тексте ошибки


def test_no_files_without_429_keeps_not_found_text(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        return _proc(stdout=f"{VIDEO_ID}|T", stderr="WARNING: no subtitles")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)
    result = run.main(f"https://youtu.be/{VIDEO_ID}")

    assert result["error"].startswith("субтитры не найдены")
    assert "429" not in result["error"]
