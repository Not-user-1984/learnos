# LearnOS Agent

Персональная система обучения с ИИ: ресерч источников → курс-план → сессии 30–40 мин (теория + фейнман-вопросы + практика) → блок в базе знаний рождается ТОЛЬКО после сессии.

**Обязательное чтение перед работой:**

- [PLAN.md](PLAN.md) — идея, фазы, зафиксированные решения (§6)
- [ARCHITECTURE.md](ARCHITECTURE.md) — компоненты, модель данных, MCP-инструменты, стейт-машина сессии

## Текущий статус (2026-10-06, фаза 0)

Решения зафиксированы, кода ещё нет. Следующий шаг — фаза 0/1 (PLAN.md §4):

1. Skeleton `server/`: FastAPI + SQLite (модель из ARCHITECTURE.md §2) + MCP streamable HTTP
2. Skeleton `web/`: Next.js + TS strict, типы API из OpenAPI
3. Скилл-система `server/skills/` (drop-in, авт. регистрация как MCP-инструментов) + порты `youtube-to-summary`, `web-search`
4. `book-splitter`: PDF → TOC (pymupdf) → главы → чанки-файлы + summary на главу
5. Петля MVP: сессию водит opencode через MCP, блок пишется как markdown + frontmatter в `kb/`

## Зафиксированные решения

- Скиллы — внутри сервиса: `server/skills/<name>/` (SKILL.md + run.py), drop-in, видны из всех каналов (MCP/веб/встроенный агент)
- Harness (opencode и пр.) — клиенты, не фундамент; ядро самодостаточно
- UI базы знаний: свой веб-UI с фазы 0/1 (Next.js + TS strict, типы из OpenAPI; MD + mermaid сразу, React Flow — фаза 2)
- Мобильный канал: веб-чат самого сервиса (сервис сам зовёт LLM)
- LLM: z.ai GLM (OpenAI-совместимый API), без fallback в v1
- Фаза 1 целиком на маке; деплой на хомлаб — фаза 2
- Git: только код и `kb/*.md`; книги/транскрипты в git не попадают

## Как запустить (прототип)

```bash
cd server
uv sync
uv run uvicorn app.main:app --port 8765
```

- REST: `http://localhost:8765/api/*` (курсы/сессии/блоки/скиллы)
- MCP: `http://localhost:8765/mcp` (streamable HTTP, 12+ инструментов)
- Петля: `POST /api/courses` → `POST /api/sources` → `POST /api/sessions?course_id=N` → `advance` (theory_done → ask/answer → go_practice → practice_done) → `finish` с драфтом блока → файл в `kb/`
- Скиллы: `server/skills/<name>/` (SKILL.md + run.py), подхватываются на старте, видны через `/api/skills` и MCP `list_skills`/`run_skill`

## Хомлаб (для фазы 2 и песочниц)

Репо автоматизации: `~/my_dev/my_servak/proxmox` (читать его AGENTS.md перед работой с сервером).

- Proxmox host: `192.168.0.105`, сеть `192.168.0.0/24`, CT со статическими IP
- Управление CT/VM: `python3 ~/my_dev/my_servak/proxmox/scripts/python/runtime/pve.py` (status/start/stop/exec/push/pull) — логику переиспользовать для `create_sandbox`
- Роуты: запись в `services.json` → `./scripts/run.sh automation sync-all` (NPM hginx + Dashy + health). Планируемый роут: `learn.not-user-1984.duckdns.org`
- Доступ с мобилки: Tailscale (Pixel 9 уже в tailnet), публично не светим
- ⚠️ Сон сервера 19:00–08:30 (systemd homelab-sleep). Разбудить: `python3 ~/my_dev/my_servak/proxmox/scripts/mac/wake.py` — только из LAN. Вопрос сдвига сна — открыт (PLAN.md §6.3)
- OpenClaw на host-docker:18000 — потенциальный канал сессий, пока не используем

## Готовые скиллы для портирования

- YouTube → транскрипт: `~/my_dev/radmipa-skills/skills/youtube-to-summary/SKILL.md` (yt-dlp субтитры, fallback Whisper)
- Web-поиск: `~/my_dev/radmipa-skills/skills/web-search/SKILL.md` (для `research_sources`)

## Секреты

- Только через `sec` (macOS Keychain, `~/.local/bin/sec`): `sec set` / `sec exec NAME -- CMD`
- Никогда не хардкодить ключи (LLM API, Proxmox token) и не печатать значения
- См. `secrets-map` скилл, если непонятно где что лежит

## Правила

- Блок KB создаётся только через завершённую сессию — это ядро продукта, не обходить
- Контекст LLM не захламлять: книги читаются по главам через `read_chapter`, не целиком
- Коммиты — только по явной просьбе пользователя
- Язык общения с пользователем и документации — русский
