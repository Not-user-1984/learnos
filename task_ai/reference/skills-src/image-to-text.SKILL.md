---
name: image-to-text
description: "OCR картинок: читает текст с изображений через GPT-4o Vision или GLM-4.6V"
no-export: [cursor]
evolution: true
version: 1.0
status: active
created: 2026-08-12
---

# Image-to-Text (vision)

Extract text AND analyze images via **OpenAI GPT-4o** or **z.ai GLM-4.6V**.

## Provider selection (auto by default)

| Flag | Behavior |
|------|----------|
| (none) `--provider auto` | Try OpenAI first; if unreachable (no VPN) → fall back to **z.ai GLM-4.6V** |
| `--provider openai` | Force OpenAI GPT-4o (needs VPN / reachable api.openai.com) |
| `--provider zai` | Force z.ai GLM-4.6V (works **without VPN**, via GLM Coding Plan) |

Keys are auto-loaded — no setup needed:
- OpenAI: `OPENAI_API_KEY` from env or `~/.config/opencode/.env`
- z.ai: `zai-coding-plan` entry from `~/.local/share/opencode/auth.json`

## Default screenshot location

macOS screenshots are saved to `~/scrin_video/`. When the user says посмотри скриншот", "прочитай последние N скринов" without a path — search there.

## Commands

### Latest N screenshots (no path needed)
```bash
# Look at the 5 most recent screenshots
python3 ~/.config/opencode/tools/image_to_text.py --latest 5 --stdout
# Just the most recent one
python3 ~/.config/opencode/tools/image_to_text.py --latest 1 --stdout
# Save .md for each into a folder
python3 ~/.config/opencode/tools/image_to_text.py --latest 5 -o ~/scrin_video/output/
```

### Specific image — OCR (default)
```bash
python3 ~/.config/opencode/tools/image_to_text.py /path/to/image.png --stdout
python3 ~/.config/opencode/tools/image_to_text.py /path/to/image.png -o /path/to/output/
```

### Describe everything (not just text)
```bash
python3 ~/.config/opencode/tools/image_to_text.py /path/to/image.png --describe --stdout
```

### Custom question / prompt
```bash
python3 ~/.config/opencode/tools/image_to_text.py /path/to/image.png \
  --prompt "Сколько квартир видно на фото? Опиши состояние ремонта." --stdout
```

### JSON output (includes provider + usage)
```bash
python3 ~/.config/opencode/tools/image_to_text.py /path/to/image.png --json
```

### Force a provider
```bash
python3 ~/.config/opencode/tools/image_to_text.py IMG.png --provider zai --stdout
python3 ~/.config/opencode/tools/image_to_text.py IMG.png --provider openai --stdout
```

## Supported formats
PNG, JPG, JPEG, WebP, BMP, TIFF, GIF

## Notes
- `auto` mode does a quick reachability check on api.openai.com (4s). If VPN is off, it silently uses z.ai — no user action needed.
- For long sessions without VPN, prefer `--provider zai` to skip the reachability check.
- z.ai GLM-4.6V is available through the GLM Coding Plan (no extra charge, no VPN).
- Each image is processed individually; `--latest N` processes them newest-first.

---

## 🔁 Эволюция этого скилла (не удалять — протокол жизненного цикла)

- **Сработал** → `python3 ~/my_dev/radmipa-skills/sync.py used image-to-text`
- **Наврал/сломался** → почини прямо сейчас в этой же сессии, затем
  `sync.py used image-to-text --fail "что случилось"`, подними `version` на 0.1
- **Паттерн устарел** → предложи архивацию в draft-заметке куратору
- Куратор (ночной аудит) сверяет этот блок с usage-логом и чинит мелочи сам
