#!/usr/bin/env python3
"""YouTube URL -> полный текст (субтитры, fallback Whisper) в Markdown.

Источник логики: ~/my_dev/StadiaAi/backend/app/services/youtube_parser.py
(интегрировано и расширено: title/duration, ручные субтитры, Whisper-fallback).

Использование:
    python3 youtube_to_text.py <URL> [-o DIR] [--lang ru,en] [--stdout] [--force-whisper]
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ENV_FILE = Path.home() / ".config" / "opencode" / "opencode.env"
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_CHUNK_SEC = 600
DEFAULT_OUT_DIR = Path.home() / "scrin_video" / "output"
SOCKS_HOST, SOCKS_PORT = "127.0.0.1", 7890  # mihomo (Clash Party) -> VLESS-нод


def detect_proxy() -> str | None:
    """SOCKS5 7890 (mihomo/VLESS) если слушается — YouTube/OpenAI через нод."""
    try:
        with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=1):
            return f"socks5h://{SOCKS_HOST}:{SOCKS_PORT}"
    except OSError:
        return None


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def video_metadata(url: str, proxy: str | None) -> dict:
    try:
        out = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist",
             *(["--proxy", proxy] if proxy else []), url],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout.splitlines()[0])
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return {}


def _clean_subs(content: str) -> str:
    lines = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.isdigit() and len(line) <= 4:
            continue
        if "-->" in line:
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if line.startswith("<"):
            line = re.sub(r"<[^>]+>", "", line).strip()
            if not line:
                continue
        lines.append(line)
    return " ".join(lines)


def fetch_subtitles(url: str, work_dir: Path, languages: list[str], proxy: str | None) -> tuple[str, str] | None:
    """Возвращает (text, lang) или None."""
    tmpl = str(work_dir / "sub")
    for lang in languages:
        for auto_flag in ("--write-sub", "--write-auto-subs"):
            cmd = [
                "yt-dlp", auto_flag, "--sub-lang", lang,
                "--skip-download", "--convert-subs", "vtt",
                "--no-playlist", *(["--proxy", proxy] if proxy else []),
                "-o", tmpl, url,
            ]
            try:
                subprocess.run(cmd, capture_output=True, text=True,
                               timeout=180, check=False)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            for ext in ("vtt", "srt"):
                f = work_dir / f"sub.{lang}.{ext}"
                if f.exists():
                    text = _clean_subs(f.read_text(encoding="utf-8", errors="ignore"))
                    text = _dedupe_lines(text)
                    if text.strip():
                        return text.strip(), lang
    return None


def _dedupe_lines(text: str) -> str:
    """Автосубтитры VTT дублируют строки скроллом — схлопываем повторы."""
    words = text.split()
    out = []
    i = 0
    step = 8
    while i < len(words):
        window = words[i:i + step]
        if out and window and " ".join(window[:4]) == " ".join(out[-4:]):
            i += step
            continue
        out.extend(window)
        i += step
    return " ".join(out)


def load_api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    for env_path in (ENV_FILE, Path.home() / ".config" / "opencode" / ".env"):
        if env_path.exists():
            for line in env_path.read_text().strip().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == "OPENAI_API_KEY":
                    return v.strip()
    return None


def whisper_transcribe(audio_path: Path, language: str | None, proxy: str | None) -> str:
    key = load_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY не найден (нужен для Whisper-fallback)")

    with tempfile.TemporaryDirectory() as chunk_dir_s:
        chunk_dir = Path(chunk_dir_s)
        duration = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            text=True).strip())
        parts = []
        idx, start = 0, 0.0
        while start < duration:
            chunk = chunk_dir / f"chunk_{idx:04d}.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path), "-ss", str(start),
                 "-t", str(WHISPER_CHUNK_SEC), "-acodec", "libmp3lame",
                 "-ab", "64k", "-ar", "16000", "-ac", "1", str(chunk)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with open(chunk, "rb") as fh:
                resp = requests.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (chunk.name, fh, "audio/mpeg")},
                    data={"model": "whisper-1",
                          **({"language": language} if language else {})},
                    proxies={"http": proxy, "https": proxy} if proxy else None,
                    timeout=600,
                )
                resp.raise_for_status()
                parts.append(resp.json()["text"].strip())
            print(f"  whisper: chunk {idx + 1} готов", file=sys.stderr)
            idx += 1
            start += WHISPER_CHUNK_SEC
        return " ".join(parts)


def download_audio(url: str, work_dir: Path, proxy: str | None) -> Path:
    audio = work_dir / "audio.m4a"
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
         "--no-playlist", *(["--proxy", proxy] if proxy else []),
         "-o", str(audio), url],
        check=True, capture_output=True, text=True, timeout=1800)
    return audio


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "video"


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube -> текст (субтитры/Whisper)")
    parser.add_argument("url", help="YouTube URL или ID видео")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--lang", default="ru,en", help="языки субтитров через запятую (default: ru,en)")
    parser.add_argument("--stdout", action="store_true", help="печать текста в stdout вместо файла")
    parser.add_argument("--force-whisper", action="store_true", help="игнорировать субтитры, транскрибировать аудио")
    parser.add_argument("--title", default=None, help="заголовок для вывода (иначе из метаданных)")
    parser.add_argument("--no-proxy", action="store_true", help="не использовать SOCKS5 7890 (mihomo/VLESS)")
    args = parser.parse_args()

    url = args.url if is_youtube_url(args.url) else f"https://www.youtube.com/watch?v={args.url}"
    languages = [x.strip() for x in args.lang.split(",") if x.strip()]

    proxy = None if args.no_proxy else detect_proxy()
    if proxy:
        print(f"Прокси: {proxy} (YouTube/Whisper через VLESS-нод)", file=sys.stderr)

    meta = video_metadata(url, proxy)
    title = args.title or meta.get("title") or "YouTube video"
    duration = meta.get("duration") or 0

    source = None
    text = None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if not args.force_whisper:
            result = fetch_subtitles(url, work, languages, proxy)
            if result:
                text, source = result[0], f"subtitles:{result[1]}"
        if text is None:
            print("Субтитры не найдены, запускаю Whisper...", file=sys.stderr)
            audio = download_audio(url, work, proxy)
            text = whisper_transcribe(audio, languages[0] if len(languages) == 1 else None, proxy)
            source = "whisper"

    if not text.strip():
        print("Error: не удалось получить текст", file=sys.stderr)
        sys.exit(1)

    dur_h, dur_m = duration // 3600, (duration % 3600) // 60
    header = f"# {title}\n\n- URL: {url}\n- Источник текста: {source}\n"
    if duration:
        header += f"- Длительность: {int(dur_h):02d}:{int(dur_m):02d}:{int(duration % 60):02d}\n"
    body = header + f"\n## Текст\n\n{text}\n"

    if args.stdout:
        print(body)
        return

    args.output.mkdir(parents=True, exist_ok=True)
    out_file = args.output / f"{slugify(title)}-{source.split(':')[-1]}.md"
    out_file.write_text(body, encoding="utf-8")
    print(out_file)


if __name__ == "__main__":
    main()
