#!/usr/bin/env python3
"""Extract text / analyze images via OpenAI GPT-4o Vision OR z.ai GLM-4.6V.

Provider selection (--provider):
  auto   (default) — try OpenAI (needs VPN); on connection failure fall back to z.ai
  openai           — force OpenAI GPT-4o
  zai              — force z.ai GLM-4.6V (works WITHOUT VPN, via GLM Coding Plan)

Keys are auto-loaded:
  OpenAI: OPENAI_API_KEY from env or ~/.config/opencode/.env
  z.ai  : "zai-coding-plan" entry from ~/.local/share/opencode/auth.json

Modes:
  image_to_text.py IMG.jpg                      # OCR (default), stdout
  image_to_text.py IMG.jpg --describe           # full description (not just text)
  image_to_text.py IMG.jpg --prompt "..."       # custom question/prompt
  image_to_text.py --latest 5                   # last 5 screenshots from ~/scrin_video/
  image_to_text.py IMG.jpg -o out/              # write .md to folder
  image_to_text.py IMG.jpg --json               # JSON with usage/provider
"""
import argparse
import base64
import glob
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import requests

ENV_FILE = Path.home() / ".config" / "opencode" / ".env"
AUTH_FILE = Path.home() / ".local" / "share" / "opencode" / "auth.json"
SCREENSHOTS_DIR = Path.home() / "scrin_video"

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ZAI_URL = "https://api.z.ai/api/coding/paas/v4/chat/completions"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif", ".heic"}


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
            v = v[1:-1]
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v


def get_openai_key():
    k = os.getenv("OPENAI_API_KEY")
    if k:
        return k
    print("Error: OPENAI_API_KEY not found", file=sys.stderr)
    sys.exit(1)


def get_zai_key():
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text())
        entry = data.get("zai-coding-plan") or data.get("zai")
        if entry and entry.get("key"):
            return entry["key"]
    print("Error: z.ai key not found in auth.json", file=sys.stderr)
    sys.exit(1)


def encode_image(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def build_payload(model, b64, prompt):
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a vision assistant. Respond in Russian unless asked otherwise."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": b64}},
                {"type": "text", "text": prompt},
            ]},
        ],
        "max_tokens": 4096,
    }


def call_openai(b64, prompt):
    resp = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {get_openai_key()}"},
        json=build_payload("gpt-4o", b64, prompt),
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def call_zai(b64, prompt):
    body = build_payload("glm-4.6v", b64, prompt)
    body["thinking"] = {"type": "disabled"}
    resp = requests.post(
        ZAI_URL,
        headers={"Authorization": f"Bearer {get_zai_key()}", "Content-Type": "application/json"},
        json=body,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def is_openai_reachable(timeout=4):
    try:
        requests.get("https://api.openai.com/v1/models", timeout=timeout)
        return True
    except requests.exceptions.RequestException:
        return False


def run(image_path, provider, prompt):
    b64 = encode_image(image_path)
    used = None
    if provider == "openai":
        text, usage = call_openai(b64, prompt)
        used = "openai"
    elif provider == "zai":
        text, usage = call_zai(b64, prompt)
        used = "zai"
    else:  # auto
        if is_openai_reachable():
            try:
                text, usage = call_openai(b64, prompt)
                used = "openai"
            except Exception as e:
                print(f"[auto] OpenAI не сработал ({e}); пробую z.ai...", file=sys.stderr)
                text, usage = call_zai(b64, prompt)
                used = "zai"
        else:
            print("[auto] OpenAI недоступен (нет VPN?) — использую z.ai GLM-4.6V", file=sys.stderr)
            text, usage = call_zai(b64, prompt)
            used = "zai"
    return {"text": text, "usage": usage, "provider": used, "source": str(image_path)}


def find_latest_screenshots(n):
    files = []
    for ext in IMAGE_EXTS:
        files.extend(glob.glob(str(SCREENSHOTS_DIR / f"*{ext}")))
    files = [f for f in files if os.path.isfile(f)]
    files.sort(key=os.path.getmtime, reverse=True)
    return files[:n]


def process(path, args):
    prompt = args.prompt
    if args.describe:
        prompt = "Подробно опиши, что изображено на картинке: объекты, текст, контекст, детали. Отвечай на русском."
    elif prompt is None:
        prompt = "Извлеки весь текст с изображения. Верни только распознанный текст, сохраняя структуру. Отвечай на русском."
    return run(Path(path), args.provider, prompt)


def write_md(image_path, result, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{Path(image_path).stem}.md"
    out.write_text("\n".join([
        f"# {Path(image_path).name} ({result['provider']})", "",
        f"- **Source**: {image_path}", "",
        "---", "",
        result["text"],
    ]), encoding="utf-8")
    return out


def main():
    p = argparse.ArgumentParser(description="Image → text via OpenAI or z.ai (auto-fallback)")
    p.add_argument("image", nargs="?", help="Path to image file")
    p.add_argument("--latest", type=int, metavar="N", help="Process N most recent screenshots from ~/scrin_video/")
    p.add_argument("-o", "--output", type=Path, help="Output directory for .md files")
    p.add_argument("-l", "--language", help="Language hint (legacy, ignored)")
    p.add_argument("--provider", choices=("auto", "openai", "zai"), default="auto")
    p.add_argument("--describe", action="store_true", help="Full description instead of OCR")
    p.add_argument("--prompt", help="Custom prompt/question about the image")
    p.add_argument("--stdout", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    load_env()

    targets = []
    if args.latest:
        targets = find_latest_screenshots(args.latest)
        if not targets:
            print(f"В {SCREENSHOTS_DIR} изображений не найдено.")
            return
        print(f"Найдено {len(targets)} свежих скринов:", file=sys.stderr)
    elif args.image:
        img = Path(args.image).resolve()
        if not img.exists():
            print(json.dumps({"error": f"Image not found: {img}"}) if args.json else f"Image not found: {img}")
            sys.exit(1)
        targets = [str(img)]
    else:
        p.error("Нужен путь к картинке или --latest N")

    results = []
    for i, t in enumerate(targets, 1):
        if len(targets) > 1:
            print(f"\n[{i}/{len(targets)}] {Path(t).name}", file=sys.stderr)
        try:
            res = process(t, args)
        except Exception as e:
            res = {"source": t, "error": str(e)}
            print(f"  ОШИБКА: {e}", file=sys.stderr)
        results.append(res)
        if "error" in res:
            continue
        if args.json:
            continue
        if args.stdout or not args.output:
            print(res["text"])
        if args.output:
            out = write_md(t, res, args.output)
            print(f"→ {out}")
        if len(targets) > 1 and not args.stdout:
            print(res["text"][:200] + ("..." if len(res["text"]) > 200 else ""))

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
