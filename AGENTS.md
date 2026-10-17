# LearnOS Agent

Персональная система обучения с ИИ: ресерч источников → курс-план → сессии 30–40 мин (теория + фейнман-вопросы + практика) → блок в базе знаний рождается ТОЛЬКО после сессии.

**Обязательное чтение перед работой:**

- [README.md](README.md) — **карта всей системы**: архитектура, запуск, прод, воркфлоу разработки
- [task_ai/README.md](task_ai/README.md) — ТЗ на развитие (источник истины для цели): этапы, архитектура, правила кода; раздел «Изменения ТЗ» — читать при каждом новом этапе
- [task_ai/tasks/README.md](task_ai/tasks/README.md) — система задач агента: `tasks/` (открытые), `archive/` (история выполненного); воркфлоу «код → тесты → push → деплой → закрыть таску → обновить доку»
- [PLAN.md](PLAN.md) — идея, фазы, зафиксированные решения (§6)
- [ARCHITECTURE.md](ARCHITECTURE.md) — компоненты, модель данных, MCP-инструменты, стейт-машина сессии

**Агент-разработчик**: `.zcode/agents/learnos-dev.md` — субагент, знающий архитектуру и воркфлоу; запускать задачи разработки через него.

## Текущий статус (2026-10-13, этапы 1–6 ТЗ выполнены)

Сервер переписан в модульный монолит (9 модулей, слои domain/service/infra, единый ToolRegistry → MCP `/mcp` + `/mcp/<module>` + агенты), схема v2 с миграциями Alembic, LLM-слой z.ai GLM (chat/structured/fast) и агентный рантайм (тьюторы чата, block_writer, categorizer, chapter_summarizer, course_planner; трейсы в `agent_runs`). Веб: чат с SSE и карточками, база знаний (категории/входящие/версии), библиотека (PDF/YouTube + читалка), курсы (прогресс + планировщик), настройки. Всё живёт в Docker Compose; живые сценарии (быстрый разбор → конспект, сессия → урок, планировщик курса, экспорт) прогнаны на GLM. Тесты: 87 (unit/integration/api/contract/agent), ruff 0, import-linter 3 контракта.

Из незакрытого — смотреть живой бэклог: [task_ai/tasks/](task_ai/tasks/) (полный mypy, sqlite-vec, доступ с мобилки, остатки этапов 8–11 и пр.).

## Зафиксированные решения

- Скиллы — внутри сервиса: `server/skills/<name>/` (SKILL.md + run.py), drop-in, видны из всех каналов (MCP/веб/встроенный агент)
- Harness (opencode и пр.) — клиенты, не фундамент; ядро самодостаточно
- UI базы знаний: свой веб-UI с фазы 0/1 (Next.js + TS strict, типы из OpenAPI; MD + mermaid сразу, React Flow — фаза 2)
- Мобильный канал: веб-чат самого сервиса (сервис сам зовёт LLM)
- LLM: z.ai GLM (OpenAI-совместимый API), без fallback в v1
- Фаза 1 целиком на маке; деплой на хомлаб — фаза 2
- Git: только код и `kb/*.md`; книги/транскрипты в git не попадают

## Как запустить (прототип)

## Как запустить

**Docker (основной способ):**

```bash
docker compose build
~/.local/bin/sec exec ZAI_API_KEY -- docker compose up -d   # с ключом GLM; без sec — LLM выключен, сервис работает
# web: http://localhost:3000 · REST: http://localhost:8765/api · MCP: http://localhost:8765/mcp
```

**Локально (разработка):**

```bash
cd server && uv sync && uv run uvicorn app.main:app --port 8765   # миграции применяются на старте
cd web && npm install && npm run dev                              # LEARNOS_API_URL, по умолчанию http://localhost:8765
```

- Проверка сервера: `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- Проверка веба: `cd web && npm run lint && npx tsc --noEmit && npm run build`; типы API: `npm run gen:api`
- Живой LLM-smoke: `sec exec ZAI_API_KEY -- uv run python -m app.cli smoke-llm` (или в контейнере)
- CLI: `uv run python -m app.cli migrate|reindex|smoke-llm|seed-demo`

## Ключевые эндпоинты

- REST: `/api/health`, `/api/conversations` (+`/{uid}/messages` SSE, `/stop`), `/api/kb/*` (блоки/категории/входящие/версии/reindex), `/api/sources` (+`/upload`, `/{id}/process`, главы), `/api/activities`, `/api/sessions` (+advance/finish), `/api/courses` (+`/plan`, `/from-plan`, items), `/api/search`, `/api/export`
- MCP: `/mcp` (все ~40 инструментов) и `/mcp/<module>` (knowledge, library, learning, chat, courses, profile, search, export, skills)
- Чат-режимы: free / quick / session; сессия-урок создается первым сообщением в разговоре session-режима
- Скиллы: `server/skills/<name>/` (web-search, book-splitter, youtube-to-summary) — те же, что и раньше, видны в MCP и агентам

## Хомлаб (для фазы 2 и песочниц)

**Прод-стенд LearnOS (с 2026-10-17): CT 132 `learnos` — web http://192.168.0.132:3000, API http://192.168.0.132:8765 (LAN).**

- Развёрнут `~/my_dev/my_servak/proxmox/scripts/deploy/deploy-learnos-container.sh` (4c/6G/30G SSD256, docker compose внутри CT; ZAI_API_KEY и GitHub-токен проброшены на CT файлами через `sec exec`, не печатаются)
- **Разработка = git push**: на CT таймер `learnos-deploy.timer` каждые 2 мин делает fetch; есть новые коммиты в main → reset/build/up + health. Логи: `journalctl -u learnos-deploy.service`, `/var/log/learnos-deploy.log`
- Данные (`/opt/learnos/{data,kb}` на CT) в git не попадают
- YouTube-скилл ходит через хомлаб-прокси `LEARNOS_YT_PROXY=socks5://192.168.0.10:1080` (vpn-gw, CT 103)
- В services.json хомлаба: `route:false` (только Dashy/health), публичного домена нет; с мобилки — после Tailscale-роутинга

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
