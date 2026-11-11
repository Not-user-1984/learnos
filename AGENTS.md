# LearnOS Agent

Персональная система обучения с ИИ: ресерч источников → курс-план → сессии 30–40 мин (теория + фейнман-вопросы + практика) → блок в базе знаний рождается ТОЛЬКО после сессии.

**Обязательное чтение перед работой:**

- [README.md](README.md) — **карта всей системы**: архитектура, запуск, прод, воркфлоу разработки
- [task_ai/README.md](task_ai/README.md) — ТЗ на развитие (источник истины для цели): этапы, архитектура, правила кода; раздел «Изменения ТЗ» — читать при каждом новом этапе
- [task_ai/tasks/README.md](task_ai/tasks/README.md) — система задач агента: `tasks/` (открытые), `archive/` (история выполненного); воркфлоу «код → тесты → push → деплой → закрыть таску → обновить доку»
- [PLAN.md](PLAN.md) — идея, фазы, зафиксированные решения (§6)
- [ARCHITECTURE.md](ARCHITECTURE.md) — компоненты, модель данных, MCP-инструменты, стейт-машина сессии

**Агент-разработчик**: `.zcode/agents/learnos-dev.md` — субагент, знающий архитектуру и воркфлоу; запускать задачи разработки через него.

## bridge_ai_agent (вспомогательно)

Общая папка конвейера «архитектор → исполнитель». Обращайся к ней, только если тебя явно попросили
(«посмотри bridge», «исполняй», «возьми B-NNN») или запустили с такой задачей: тогда следуй
`bridge_ai_agent/README.md`. Без этого работай с проектом как обычно: bridge не жди и не меняй.

## Текущий статус

Подробный статус (что сделано по этапам и аудиту, что в бэклоге) — [STATUS.md](STATUS.md): читать при старте
задачи разработки, обновлять **там** после закрытия задачи. Живой бэклог — [task_ai/tasks/](task_ai/tasks/),
баги — [task_ai/bugs/](task_ai/bugs/). Прод — CT 132, автодеплой по push в main (см. «Хомлаб»).

## Зафиксированные решения

- Скиллы — внутри сервиса: `server/skills/<name>/` (SKILL.md + run.py), drop-in, видны из всех каналов (MCP/веб/встроенный агент)
- Harness (opencode и пр.) — клиенты, не фундамент; ядро самодостаточно
- UI базы знаний: свой веб-UI с фазы 0/1 (Next.js + TS strict, типы из OpenAPI; MD + mermaid сразу, React Flow — фаза 2)
- Мобильный канал: веб-чат самого сервиса (сервис сам зовёт LLM)
- LLM: z.ai GLM (OpenAI-совместимый API), без fallback в v1
- Фаза 1 целиком на маке; деплой на хомлаб — фаза 2
- Git: только код и `kb/*.md`; книги/транскрипты в git не попадают
- Дизайн-система (2026-10-22): три темы (пергамент — дефолт, тёмная, светлая), иконки Material Symbols Rounded (компонент Icon), шрифты Inter/Literata; в UI не хардкодить hue-цвета — только семантические токены; гайд — [web/DESIGN.md](web/DESIGN.md)

## Как запустить

**Docker (основной способ):**

```bash
docker compose build
~/.local/bin/sec exec ZAI_API_KEY -- docker compose up -d   # с ключом GLM; без sec — LLM выключен, сервис работает
# web: http://localhost:3000 · REST: http://localhost:8765/api · MCP: http://localhost:8765/mcp
```

Опциональный auth (R-07 аудита, включён на проде): `LEARNOS_API_TOKEN` в `.env` — все
`/api` и `/mcp` требуют `Authorization: Bearer <токен>` (`/api/health` открыт; веб-прокси
Next добавляет токен на сервере, браузер его не видит). CORS-список: `LEARNOS_CORS_ORIGINS`.

Дополнительные ключи GLM опциональны: `ZAI_API_KEY_2..4` образуют цепочку фейловера — при ошибке
квоты ключ уходит в cooldown (~10 мин, `LEARNOS_LLM_KEY_COOLDOWN`) и запрос идёт следующим;
порядок цепочки = `api_key_envs` в `server/config/llm.yaml`, пустые env пропускаются.
Роли и модели — там же (`chat`=glm-5.3 думающая; `fast`/`structured`=glm-5.3-flash с
`params.thinking: disabled` — per-role params уходят в wire-запрос; пресеты OpenRouter/
OpenAI/DeepSeek закомментированы — смена провайдера правкой конфига, z.ai-специфика
только в адаптере `app/llm/providers/openai_compat.py`). Состояние цепочки — блок «LLM»
в настройках веба или `GET /api/llm/status`. Полное управление из UI — задача T-057.

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

- REST: `/api/health`, `/api/llm/status` (детальный статус LLM под bearer: роли/модели/params, цепочки ключей с cooldown — в health только сводка), `/api/conversations` (+`/{uid}/messages` SSE с `research:true` для ресёрч-запуска, `/stop`, DELETE), `/api/kb/*` (блоки/категории/входящие/версии/reindex; DELETE блока — версии+файл+индекс), `/api/sources` (+`/upload`, `/{id}/process`, главы, `/{ref}/file` PDF-оригинал inline, `/{ref}/outline` страницы глав по закладкам, DELETE), `/api/activities` (+`/mark-read` «прочитал сам» — глава в прогресс книги без разговора, DELETE), `/api/sessions` (+advance/finish/DELETE), `/api/courses` (+`/plan`, `/from-plan`, items, DELETE), `/api/search`, `/api/export`, `/api/connectivity` (+`/check` — настройки поиска/прокси из UI), `/api/research/providers` (где агент ищет: web/academic/video)
- MCP: `/mcp` (все ~78 инструментов) и `/mcp/<module>` (knowledge, library, learning, chat, courses, profile, search, export, skills, research); тул LLM-слоя `llm_status` (module="llm", общий в `/mcp`) — роли/модели + состояние цепочки ключей, `reset_cooldown=true` снимает cooldown после исчерпания квоты
- Чат: единый вход — стартовый экран /chat (новый разговор всегда root, сценарии уходят интентами review/study/session/quote/tune/reinforce с первым сообщением); legacy-режимы free/quick/session/tuning/agent:<name> живут для старых разговоров и MCP (кастомные и встроенные, например `agent:repo_scout`); сессия-урок создаётся первым сообщением в разговоре session-режима; субагенты — инструмент `run_agent` (каталог `list_agents`)
- Ревизия кода (T-038): `repo_list`/`repo_read` (секреты .env недоступны), `create_task_file`, `git_prepare_change` (ветки agent/* в worktree, guard-лист: bootstrap/main/alembic/llm/compose/web/task_ai/revision; коммит только с зелёными проверками; бюджет 3/день), `run_checks` — смонтировано read-only /repo. Ресёрч-инструменты агентов: `web_search` (цепочка), `academic_search` (агрегат arXiv + OpenAlex + Semantic Scholar: дедуп DOI/title, provider у каждой статьи, OpenAlex/S2 через прокси), `search_providers` (web/academic/video с enabled-статусами), `youtube_search` (yt-dlp → веб), `web_read`, `github_repo`/`github_file` (idea-scout)
- Скиллы: `server/skills/<name>/` (web-search, book-splitter, youtube-to-summary, torrent-fetch) — drop-in, видны в MCP и агентам. torrent_fetch: Prowlarr-поиск + qBit-загрузка; книги (категория learnos-books) при завершении сами падают в библиотеку — hook на media-CT (`/opt/media/scripts/learnos-qbit-hook.sh`, лог `/var/log/learnos-qbit-hook.log`), конфиг `data/torrent-fetch.json`; если файл раздачи сервису не виден (qBit на другом хосте), import отвечает `file_unreachable` — заливка остаётся за hook'ом. book-splitter: PDF без закладок → главы-куски по страницам (mode=pages, куратор структуры не зовётся)

## Хомлаб (для фазы 2 и песочниц)

**Прод-стенд LearnOS (с 2026-10-17): CT 132 `learnos` — web http://192.168.0.132:3000, API http://192.168.0.132:8765 (LAN).**

- Развёрнут `~/my_dev/my_servak/proxmox/scripts/deploy/deploy-learnos-container.sh` (4c/6G/30G SSD256, docker compose внутри CT; ZAI_API_KEY и GitHub-токен проброшены на CT файлами через `sec exec`, не печатаются)
- **Разработка = git push**: на CT таймер `learnos-deploy.timer` каждые 2 мин делает fetch; есть новые коммиты в main → reset → build → **CI-гейт (ruff+lint-imports+pytest в свежем образе; фейл → откат на прежний коммит, прод остаётся на старом коде)** → up + health. Логи: `journalctl -u learnos-deploy.service`
- **Репозитории-зеркала**: origin на маке пушит сразу в GitHub (`Not-user-1984/learnos`, основной — там GitHub Actions CI: server ruff/lint-imports/pytest + web eslint/tsc/build на каждый push/PR, `.github/workflows/ci.yml`) и GitVerse (`NotUser1984/learnos`, зеркало). CT тянет деплой с GitHub
- **Архитектура CI/CD** (поток, компромиссы, что не сделано): [task_ai/reference/ci-cd-architecture.md](task_ai/reference/ci-cd-architecture.md) — читать перед изменением схемы деплоя
- **Инфра-инцидент 2026-11-08..10 (починен)**: деплой CT молчал — tailscaled на Proxmox-хосте переписал хостовый `/etc/resolv.conf` на MagicDNS (100.100.100.100), недостижимый из CT → `git fetch` падал «Could not resolve host». Чинка: `tailscale set --accept-dns=false` на хосте; resolv.conf хоста и CT = `nameserver 192.168.0.1` + fallback `77.88.8.8`. Диск CT был 97% (35ГБ dangling docker-образов) → `docker image prune -f` (-32ГБ). Не поднимать `tailscale up` с accept-dns на хосте; за диском CT следить (образы копятся на каждый деплой)
- Данные (`/opt/learnos/{data,kb}` на CT) в git не попадают; отчёты idea-scout — в `data/ideas/`
- **API-токен прода** (2026-11-01): включён — прямой доступ к `:8765` (REST/MCP) требует `Authorization: Bearer <LEARNOS_API_TOKEN>`; значение — `sec reveal LEARNOS_API_TOKEN` на маке (также в `/opt/learnos/.env` на CT). Веб `:3000` работает без токена (Next-прокси)
- Прокси и ключи поиска — из UI (Настройки → «Прокси и поиск», таблица `app_settings`): vless-ключ → xray-sidecar (сервис `learnos-xray`, socks5://xray:1080), socks5/http → напрямую; применяются на лету без рестарта. Рядом блок «LLM» (T-056): роли/модели и состояние цепочки ключей, read-only. env (`TAVILY_API_KEY`, `SERPER_API_KEY`, `LEARNOS_TELEGRAM_TOKEN` в `/opt/learnos/.env`) — fallback
- В services.json хомлаба: `route:false` (только Dashy/health), публичного домена нет; с мобилки — после Tailscale-роутинга

Репо автоматизации: `~/my_dev/my_servak/proxmox` (читать его AGENTS.md перед работой с сервером).

- Proxmox host: `192.168.0.105`, сеть `192.168.0.0/24`, CT со статическими IP
- Управление CT/VM: `python3 ~/my_dev/my_servak/proxmox/scripts/python/runtime/pve.py` (status/start/stop/exec/push/pull) — логику переиспользовать для `create_sandbox`
- Роуты: запись в `services.json` → `./scripts/run.sh automation sync-all` (NPM hginx + Dashy + health). Планируемый роут: `learn.not-user-1984.duckdns.org`
- Доступ с мобилки: Tailscale (Pixel 9 уже в tailnet), публично не светим
- ⚠️ Сон сервера 19:00–08:30 (systemd homelab-sleep). Разбудить: `python3 ~/my_dev/my_servak/proxmox/scripts/mac/wake.py` — только из LAN. Вопрос сдвига сна — открыт (PLAN.md §6.3)
- OpenClaw на host-docker:18000 — потенциальный канал сессий, пока не используем

## Готовые скиллы для портирования

- YouTube → транскрипт: `~/my_dev/radmipa-skills/skills/youtube-to-summary/SKILL.md` (yt-dlp субтитры, fallback Whisper) — портирован
- Web-поиск: `~/my_dev/radmipa-skills/skills/web-search/SKILL.md` (для `research_sources`) — портирован
- Torrent-загрузка: `~/my_dev/radmipa-skills/skills/torrent-fetch/` (Prowlarr+qBit+libgen) — портирован 2026-10-22 (T-029), книги сами падают в библиотеку через hook на media-CT

## Секреты

- Только через `sec` (macOS Keychain, `~/.local/bin/sec`): `sec set` / `sec exec NAME -- CMD`
- Никогда не хардкодить ключи (LLM API, Proxmox token) и не печатать значения
- См. `secrets-map` скилл, если непонятно где что лежит

## Правила

- Блок KB создаётся только через завершённую сессию — это ядро продукта, не обходить
- Контекст LLM не захламлять: книги читаются по главам через `read_chapter`, не целиком
- Автономный режим (решение пользователя 2026-10-22): задачи разработки делаются от постановки до готового результата без промежуточных подтверждений — код → тесты → коммит/пуш → деплой → самопроверка прода → закрытие таски → обновление доки. Коммиты и пуш — часть воркфлоу, отдельная просьба не нужна. Таску закрывает агент после собственной проверки, не ждать приёмки пользователя. Пользователь — заказчик: даёт задачу, получает отчёт с готовым результатом
- Язык общения с пользователем и документации — русский
