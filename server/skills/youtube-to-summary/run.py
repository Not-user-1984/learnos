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


def _flush_cue(cue: list, seen: set, out: list) -> None:
    text = " ".join(cue).strip()
    if text and text not in seen:
        seen.add(text)
        out.append(text)


def main(url: str) -> dict:
    out_dir = DATA_DIR / "youtube"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "ru,en",
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
    if not subs:
        return {
            "error": "субтитры не найдены (ru/en), Whisper-fallback не реализован",
            "video_id": video_id,
            "title": title,
            "stderr": (proc.stderr or "")[-200:],
        }

    raw = subs[0].read_text(encoding="utf-8", errors="replace")
    text = _parse_vtt(raw)
    md_path = out_dir / f"{video_id}.md"
    md_path.write_text(f"# {title}\n\nИсточник: {url}\n\n{text}\n", encoding="utf-8")
    return {
        "ok": True,
        "video_id": video_id,
        "title": title,
        "lang": subs[0].suffixes[0].lstrip("."),
        "chars": len(text),
        "path": str(md_path),
        "preview": text[:500],
    }
