# LearnOS Agent

Персональная система обучения с ИИ: ресерч источников → курс-план → сессии 30–40 мин (теория + фейнман-вопросы + практика) → блок в базе знаний рождается ТОЛЬКО после сессии.

**Обязательное чтение перед работой:**

- [README.md](README.md) — **карта всей системы**: архитектура, запуск, прод, воркфлоу разработки
- [task_ai/README.md](task_ai/README.md) — ТЗ на развитие (источник истины для цели): этапы, архитектура, правила кода; раздел «Изменения ТЗ» — читать при каждом новом этапе
- [task_ai/tasks/README.md](task_ai/tasks/README.md) — система задач агента: `tasks/` (открытые), `archive/` (история выполненного); воркфлоу «код → тесты → push → деплой → закрыть таску → обновить доку»
- [PLAN.md](PLAN.md) — идея, фазы, зафиксированные решения (§6)
- [ARCHITECTURE.md](ARCHITECTURE.md) — компоненты, модель данных, MCP-инструменты, стейт-машина сессии

**Агент-разработчик**: `.zcode/agents/learnos-dev.md` — субагент, знающий архитектуру и воркфлоу; запускать задачи разработки через него.

## Текущий статус (2026-11-10)

**Аудит 2026-11-01 ЗАКРЫТ ЦЕЛИКОМ (спринты 0–4, T-048..T-052)** ([task_ai/reference/audit-2026-11-01.md](task_ai/reference/audit-2026-11-01.md), 31 пункт R-01..R-31): T-048 спринт 0 (P0: обрезка окон чтения не рвёт next_offset, update_block round-trip без потерь, finish_session пишет блок до закрытия, линтер «промпт ↔ инструменты», list_blocks с tags/sources, recovery залипших processing, Telegram-фиксы) и T-049 спринт 1 (безопасность: карточки субагентов в SSE родителя, песочница скиллов без секретов + /repo-маски, SSRF-netguard на всех загрузках URL, bearer LEARNOS_API_TOKEN). Спринты 2 и 3 закрыты 2026-11-01 (T-050 harness; T-051 обучение: фейнман-гейт can_finish+verified, SRS-фиксы, поиск OR/bm25+префиксы, ингест fenced-код+map-reduce, concepts/assessments-таблицы). Спринт 2: handoff разговоров (conversations.active_agent + handoff()/handoff_back(), бейдж в чате), слой контекста (трасса инструментов и карточки в истории, компактация conversation_summarizer, бюджет 2.5 симв/токен), трейсы agent_steps + /api/runs/{id}, eval-каркас tests/evals + scripts/run_evals.py; спринты 3 (T-051) и 4 (T-052) тоже закрыты: T-051 — обучение (фейнман-гейт+verified, SRS, поиск, ингест, concepts/assessments); T-052 — эксплуатация (fail-fast миграции с бэкапом БД, healthcheck, kb/ отдельное git-репо + ежедневный бэкап, R-16/R-23/R-25..31, LLM-слой: сборка tool-call по index + фоновая петля + статус всех ролей). Остальное — как было:


Сервер — модульный монолит (14 модулей + LLM-слой, слои domain/service/infra, единый ToolRegistry → REST + MCP `/mcp` + `/mcp/<module>`, ~78 инструментов), схема Alembic до 0011, LLM z.ai GLM с цепочкой ключей (4 шт., ротация при квоте, llm_keys в health); роли разделены по моделям (T-056/BB-003): `chat`=glm-5.3 думающая (диалог обучения, разбор, фейнман), `fast`/`structured`=glm-5.3-flash + `params.thinking: disabled` (пер-role params из llm.yaml уходят в wire-запрос, bad_request на параметр — дроп без зацикливания; пресеты OpenRouter/OpenAI/DeepSeek закомментированы — смена провайдера правкой конфига); детальный статус `GET /api/llm/status` (bearer; health без детализации) и тул `llm_status` (reset_cooldown — агент сам снимает cooldown ключей); агентный рантайм с трейсами в `agent_runs` (падение инструмента не роняет агент; субагенты: `run_agent`/`list_agents`, связь трейсов `parent_run_id`, глубина ≤2). Корневой агент-оркестратор `root` — дефолтный режим новых разговоров; идёт эпик T-034 (Harness-архитектура): T-035 субагенты, T-036 умный вход, T-037 песочница скиллов и T-039 новый дизайн чата (единый вход: стартовый экран, интенты, сценарии) — в main; эпик T-034 ЗАКРЫТ целиком (T-035..T-039 + T-038 ревизия: auditor read-only по /repo, git-ветки agent/* через worktree с guard-листом и гваром зелёных проверок) песочница скиллов `data/agent-skills` → T-039 новый дизайн чата → T-038 ревизия; работа в ветке `t-034-orchestrator`, ревью и мердж — ZCode. Веб: чат с SSE (обрыв стрима → авто-догон ответа; agent_state (работает/прервано) + resume — генерация переживает уход и рестарт (T-041); инцидент-фиксы T-044: занятый разговор — 409 без дубля сообщения, бейдж с текущим инструментом + «Остановить», клик по YouTube/PDF-ссылке открывает меню действий, документы no-cache; T-045 кнопки-ответы offer_replies на закрытые вопросы агента; T-046 Э1 статус-бар прогресса книги в разборе (review_progress, отдельно от сессий) и Э2 блочная карточка разбора главы/видео (show_chapter_review); T-048: research добавляет источники только по согласию через offer_action, «О себе»/имя из профиля в блоке «Контекст»; T-054 «Прочитал сам»: кнопка в читалке помечает главу прочитанной без разбора — курсор книги и индикатор глав на странице книги (mark-read, разговор не создаётся)), база знаний с автокатегоризацией, библиотека (PDF/YouTube/веб-статьи), курсы, настройка агентов/промптов, сторонние MCP, блок «LLM» в настройках (роли/модели/params + цепочка ключей с отсчётом cooldown, T-056); удаление любых материалов с подтверждением (блоки/активности/сессии/курсы/разговоры — 409 при живых зависимостях, единый ConfirmDeleteButton). Ресёрч: цепочка поисковых провайдеров (keyless-rescue: платный по ключу → DDG → Википедия → HN — параллельный fan-out, «первый непустой побеждает», T-055), академ-агрегат academic_search (arXiv + OpenAlex + Semantic Scholar параллельно, дедуп, provider у каждой статьи; S2 без ключа регулярно 429 — тихий пропуск), youtube_search (yt-dlp → веб-фолбэк), research-режим сообщений (директива в system_extra, в чате видна только тема), тул search_providers (web/academic/video с enabled-статусами; блок «Провайдеры поиска» в настройках веба). Idea-scout: агент repo_scout (GitHub API, отчёты в data/ideas + Telegram; доступен субагентом через run_agent). Настройки связи в UI (`/api/connectivity`): ключи Tavily/Serper, socks5-прокси, vless-ключ → xray-sidecar (socks5://xray:1080 для всего стека). Скилл torrent_fetch (Prowlarr→qBit, книги learnos-books при завершении сами в библиотеке через hook media-CT; T-053: action=auto — найти и добавить лучшего одним вызовом, import — fallback hook'а: завершённая раздача → source+job напрямую в БД, идемпотентно по title; qBit 409 на повторный add = дубликат, не ошибка). Прод: Proxmox CT 132, автодеплой по git push (2 мин), тесты 450 (все спринты аудита + T-053/T-055/T-056), ruff/import-linter чистые; бэкапы: ежедневный timer 09:15 (sqlite .backup + kb tar + kb git-коммит, ротация 14); API за bearer-токеном (LEARNOS_API_TOKEN). Найденные баги продукта — реестр [task_ai/bugs/](task_ai/bugs/) (BUG-001..005 закрыты T-044; BUG-008 hook-401 — infra proxmox 067d2bc, BUG-009 PDF без TOC — T-053). Правила кода — ub-mode ([task_ai/07-code-standards.md](task_ai/07-code-standards.md), перевод [task_ai/reference/ub-mode-ru.md](task_ai/reference/ub-mode-ru.md)).

Из незакрытого — смотреть живой бэклог: [task_ai/tasks/](task_ai/tasks/) (вне аудита:  обучение — модель знания/assessments, SRS-фиксы R-17/R-18, поиск R-19, ингест R-20;  эпик «быстрый разбор v2» T-046: Э3 конспект по разговору, Э4 проверка знаний по блокам; аналогии по кнопке T-047; роли и провайдеры LLM из UI — T-057 (этап 10-B: SecretStore, БД-конфиг, hot reload; просмотр уже есть — T-056); полный mypy, sqlite-vec, ключ поиска Tavily/Serper от юзера, прокси в LAN для Telegram, скилл-система T-017, остатки ресёрча T-014 Э3–Э5). Реестр [task_ai/bugs/](task_ai/bugs/): BUG-001..009 все закрыты (T-044/T-048/T-053; BUG-008 — infra proxmox). Бах-бах-отчёт: BB-001..005 закрыты (T-054/T-055/T-056). Сырой inbox багов/фич из живого тестирования — [task_ai/bah-bah-report.md](task_ai/bah-bah-report.md): скилл «Бах-бах-Репорт» `.zcode/skills/bah-bah-report` (ZCode, фраза «запиши баг-репорт»/«запиши идею фичи») только документирует, не чинит; исправление пачкой — «запусти бах-бах на исправление» (группы без пересечений по файлам → последовательно learnos-dev).

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
- **Разработка = git push**: на CT таймер `learnos-deploy.timer` каждые 2 мин делает fetch; есть новые коммиты в main → reset → build → **CI-гейт (ruff+lint-imports+pytest в свежем образе; фейл → откат на прежний коммит, прод остаётся на старом коде)** → up + health. Логи: `journalctl -u learnos-deploy.service`, `/var/log/learnos-deploy.log`
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
