import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.paths import DATA_DIR


def _proxy_url() -> str:
    """Прокси из env (LEARNOS_YT_PROXY) — обновляется настройками UI на лету,
    поэтому читаем при каждом вызове, а не на импорте."""
    return (os.environ.get("LEARNOS_YT_PROXY") or "").strip()


def _proxy_up() -> bool:
    """Жив ли прокси-хост (TCP): например socks5://xray:1080 из настроек UI."""
    from urllib.parse import urlparse

    url = _proxy_url()
    if not url:
        return False
    parsed = urlparse(url if "://" in url else f"//{url}")
    host, port = parsed.hostname or "", parsed.port or 1080
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _parse_vtt(raw: str) -> str:
    """VTT → связный текст: чистим разметку и HTML-entity, склеиваем обрывки в абзацы."""
    import html

    cue, seen, out = [], set(), []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            if cue:
                _flush_cue(cue, seen, out)
                cue = []
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line))
        if line:
            cue.append(line)
    if cue:
        _flush_cue(cue, seen, out)
    # абзацы по ~4 реплики — читабельно и для LLM, и для читалки
    return "\n\n".join(" ".join(out[i : i + 4]) for i in range(0, len(out), 4))


def _ts_to_seconds(stamp: str) -> float:
    """VTT-таймстамп (00:01:02.500 | 01:02.500) → секунды."""
    parts = stamp.replace(",", ".").split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return 0.0
    while len(nums) < 3:
        nums.insert(0, 0.0)
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def _parse_vtt_segments(raw: str) -> list[dict]:
    """VTT → сегменты [{start, text}] для таймкодов (B-006).

    Склейка та же, что у текста (~4 реплики), start — начало первой реплики
    группы: сегменты совпадают с абзацами транскрипта, клик перематывает видео.
    """
    import html

    items: list[tuple[float, str]] = []
    cue_text: list[str] = []
    cue_start: float | None = None
    seen: set[str] = set()

    def flush() -> None:
        nonlocal cue_text, cue_start
        text = " ".join(cue_text).strip()
        if text and text not in seen and cue_start is not None:
            seen.add(text)
            items.append((cue_start, text))
        cue_text, cue_start = [], None

    for line in raw.splitlines():
        s = line.strip()
        if "-->" in s:
            if cue_text:
                flush()
            cue_start = _ts_to_seconds(s.split("-->")[0].strip())
            continue
        if not s or s.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            if cue_text:
                flush()
            continue
        clean = html.unescape(re.sub(r"<[^>]+>", "", s))
        if clean:
            cue_text.append(clean)
    if cue_text:
        flush()

    return [
        {"start": items[i][0], "text": " ".join(t for _, t in items[i : i + 4])}
        for i in range(0, len(items), 4)
    ]


def _flush_cue(cue: list, seen: set, out: list) -> None:
    text = " ".join(cue).strip()
    if text and text not in seen:
        seen.add(text)
        out.append(text)


# Оригинальные автодорожки (xx-orig) приоритетнее переводов (tlang): переводы
# YouTube режет 429, а без --ignore-errors yt-dlp прерывается на первой ошибке.
SUB_LANGS = "ru-orig,en-orig,ru,en"
_SUB_PRIORITY = ("ru-orig", "en-orig", "ru", "en")


def _video_id_from_url(url: str) -> str | None:
    """ID видео из ссылки (watch/youtu.be/shorts/live) — для чистки старых файлов."""
    m = re.search(r"(?:[?&]v=|youtu\.be/|shorts/|live/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _pick_sub(paths: list[Path]) -> Path | None:
    """Выбор дорожки: сначала оригиналы (ru → en), затем остальные (ru → en).

    Ручная и переводная дорожки неотличимы по имени файла (обе ID.ru.vtt),
    поэтому любой *-orig впереди: если оригинал есть, остальные — переводы.
    """
    by_lang: dict[str, Path] = {}
    for p in paths:
        parts = p.name.split(".")
        if len(parts) >= 3:  # <video_id>.<lang>.<vtt|srt>
            by_lang.setdefault(parts[-2], p)
    for lang in _SUB_PRIORITY:
        if lang in by_lang:
            return by_lang[lang]
    return None


def main(url: str) -> dict:
    out_dir = DATA_DIR / "youtube"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / "%(id)s.%(ext)s")

    # частичные файлы прошлых попыток не должны попасть в выбор дорожки
    stale_id = _video_id_from_url(url)
    if stale_id:
        for old in out_dir.glob(f"{stale_id}.*"):
            if old.suffix in (".vtt", ".srt"):
                old.unlink(missing_ok=True)

    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        SUB_LANGS,
        "--ignore-errors",
        "--sub-format",
        "vtt/srt/best",
        "--print",
        "%(id)s|%(title)s",
        "--no-simulate",
        "--no-playlist",
        "-o",
        tmpl,
        url,
    ]
    if _proxy_up():
        cmd += ["--proxy", _proxy_url()]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    stdout = (proc.stdout or "").strip().splitlines()
    meta = stdout[0].split("|", 1) if stdout and "|" in stdout[0] else (None, None)
    video_id, title = meta[0], meta[1] if len(meta) > 1 else ""

    if not video_id:
        return {"error": "yt-dlp failed", "stderr": (proc.stderr or "")[-400:]}

    # успех = есть хоть один файл субтитров (код возврата бывает ненулевым,
    # когда один из языков упал на 429, а остальные скачались)
    subs = sorted(out_dir.glob(f"{video_id}.*.vtt")) + sorted(out_dir.glob(f"{video_id}.*.srt"))
    picked = _pick_sub(subs)
    if picked is None:
        stderr_tail = (proc.stderr or "").strip()[-200:]
        if "429" in (proc.stderr or ""):
            base = "YouTube ограничил запросы (429), повторите позже"
        else:
            base = f"субтитры не найдены ({SUB_LANGS}), Whisper-fallback не реализован"
        return {
            "error": f"{base} | {stderr_tail}" if stderr_tail else base,
            "video_id": video_id,
            "title": title,
            "stderr": (proc.stderr or "")[-200:],
        }

    raw = picked.read_text(encoding="utf-8", errors="replace")
    text = _parse_vtt(raw)
    md_path = out_dir / f"{video_id}.md"
    md_path.write_text(f"# {title}\n\nИсточник: {url}\n\n{text}\n", encoding="utf-8")
    # таймкоды (B-006): сегменты рядом с транскриптом — читалка отдаёт их панели
    segments = _parse_vtt_segments(raw)
    (out_dir / f"{video_id}.segments.json").write_text(
        json.dumps(segments, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "ok": True,
        "video_id": video_id,
        "title": title,
        # en-orig → en: пользователь видит язык видео, а не служебный суффикс
        "lang": picked.name.split(".")[-2].removesuffix("-orig"),
        "chars": len(text),
        "path": str(md_path),
        "segments": len(segments),
        "preview": text[:500],
    }
