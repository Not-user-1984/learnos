# LearnOS Agent

Персональная система обучения с ИИ: ресерч источников → курс-план → сессии 30–40 мин (теория + фейнман-вопросы + практика) → блок в базе знаний рождается ТОЛЬКО после сессии.

**Обязательное чтение перед работой:**

- [PLAN.md](PLAN.md) — идея, фазы, зафиксированные решения (§6)
- [ARCHITECTURE.md](ARCHITECTURE.md) — компоненты, модель данных, MCP-инструменты, стейт-машина сессии

## Текущий статус (2026-10-06, фаза 1)

Ядро `server/` работает и протестировано: ингест (PDF/YouTube) + сессии + блоки. Веб-скелет `web/` (Next.js 16 + TS strict): список блоков + карточка с mermaid. Осталось из фазы 1:

1. Реальная учебная сессия через MCP (водит opencode из этого проекта — рестартни opencode, MCP подхватится)
2. sqlite-vec для семантического поиска (сейчас подстрока)
3. LLM-клиент (z.ai, ключ `ZAI_API_KEY` в sec): summary глав, генерация драфта блока из транскрипта

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

Веб (в отдельном терминале):

```bash
cd web
npm install   # если npm висит: HTTPS_PROXY=http://127.0.0.1:7890 npm install
npm run dev   # http://localhost:3000 (API — LEARNOS_API_URL, по умолчанию http://localhost:8765)
```

- Типы API: `npm run gen:api` (сервер должен быть запущен; openapi-typescript → `src/types/api.ts`)

- REST: `http://localhost:8765/api/*` (курсы/сессии/блоки/скиллы/главы/поиск)
- MCP: `http://localhost:8765/mcp` (streamable HTTP, 17+ инструментов; подключён в `opencode.json` проекта)
- Петля: `POST /api/courses` → `POST /api/sources` → `POST /api/sources/N/process` (PDF → главы; YouTube → транскрипт) → `POST /api/sessions?course_id=N` → `advance` (theory_done → ask/answer → go_practice → practice_done) → `finish` с драфтом блока → файл в `kb/`
- Чтение источника: `GET /api/sources/N/chapters` → `GET /api/sources/N/chapters/X` (порционно), `GET /api/search?q=...` (пока подстрока; sqlite-vec — фаза 1.1)
- Скиллы: `server/skills/<name>/` (SKILL.md + run.py), подхватываются на старте, видны через `/api/skills` и MCP `list_skills`/`run_skill`. Сейчас: `web-search` (DDG), `book-splitter` (PDF→главы), `youtube-to-summary` (субтитры, прокси 7890 автодетект)
- YouTube работает через SOCKS5 `127.0.0.1:7890` (mihomo) — если не запущен, качает напрямую

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
