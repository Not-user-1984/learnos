import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.paths import DATA_DIR

PROXY_HOST, PROXY_PORT = "127.0.0.1", 7890


def _proxy_up() -> bool:
    try:
        with socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=1):
            return True
    except OSError:
        return False


def _parse_vtt(raw: str) -> str:
    lines, seen = [], set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line in seen and lines and lines[-1] == line:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


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
        cmd += ["--proxy", f"socks5://{PROXY_HOST}:{PROXY_PORT}"]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    stdout = (proc.stdout or "").strip().splitlines()
    meta = stdout[0].split("|", 1) if stdout and "|" in stdout[0] else (None, None)
    video_id, title = meta[0], meta[1] if len(meta) > 1 else ""

    if proc.returncode != 0:
        return {"error": "yt-dlp failed", "stderr": (proc.stderr or "")[-400:]}

    subs = sorted(out_dir.glob(f"{video_id}.*.vtt")) + sorted(out_dir.glob(f"{video_id}.*.srt"))
    if not subs:
        return {
            "error": "субтитры не найдены (ru/en), Whisper-fallback не реализован",
            "video_id": video_id,
            "title": title,
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
