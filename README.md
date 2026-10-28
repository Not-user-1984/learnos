# LearnOS

Персональная система обучения с ИИ: загружаешь книгу (PDF) или YouTube-видео → агент разбирает источник по главам → проходишь его в чате (**быстрый разбор** или **сессия-урок** 20–30 мин: теория → фейнман-вопросы → практика → разбор) → в базе знаний появляется сжатый **блок** (понятия, тезисы, mermaid-схема, практика, что дозакрепить) с деревом категорий, тегами и версиями. Из блоков собираются курсы, всё выгружается в Markdown. Те же возможности — через MCP из любого клиента.

- **Пользователь**: Дмитрий. Язык кода-документации и общения — русский.
- **LLM**: z.ai GLM (OpenAI-совместимый API), роли chat/structured/fast в `llm.yaml`.
- **Прод**: Proxmox CT `learnos` (192.168.0.132), доступен по LAN и через NPM-роут.

## Быстрый старт

```bash
# локально (разработка)
cd server && uv sync && uv run uvicorn app.main:app --port 8765   # миграции applied на старте
cd web && npm install && npm run dev                              # http://localhost:3000

# прод (хомлаб): просто git push origin main — CT 132 сам пересоберётся (≤5 мин)

# проверки перед коммитом
cd server && uv run ruff check . && uv run pytest && uv run lint-imports
cd web && npm run lint && npx tsc --noEmit && npm run build
```

## Состав репозитория

| Путь | Что это |
|---|---|
| `server/` | FastAPI-ядро: модульный монолит, MCP, агентный рантайм, скиллы |
| `web/` | Next.js 16 + TS strict: чат с SSE и карточками, база знаний, библиотека с читалкой, курсы, настройки, PWA |
| `task_ai/` | ТЗ на развитие: `tasks/` (открытые задачи агента), `archive/` (история), `stages/` (этапы-ТЗ), справочники |
| `docs/` → нет; системные доки: [ARCHITECTURE.md](ARCHITECTURE.md), [PLAN.md](PLAN.md), [AGENTS.md](AGENTS.md) |
| `~/my_dev/my_servak/proxmox` | (вне репо) автоматизация хомлаба: деплой CT, NPM-роуты, health |

## Архитектура сервера

Модульный монолит, 15 модулей (включая revision — ревизия кода агентом). Порядок = порядок зависимостей (`app/bootstrap.py`):

| Модуль | Ответственность |
|---|---|
| `profile` | профиль пользователя: железо (машины для практики), предпочтения обучения |
| `research` | поиск и чтение веба: цепочка провайдеров (Tavily/Serper по ключу → ddg → Википедия → HN), академ-агрегат arXiv + OpenAlex + Semantic Scholar (дедуп, provider у каждой статьи), youtube_search, GitHub-ридер idea-scout, прозрачность поиска (`search_providers`: web/academic/video с enabled-статусами), настройки связи (`/api/connectivity`): ключи поиска, socks5-прокси, vless → xray-sidecar |
| `skills` | drop-in скиллы `server/skills/<name>/` (SKILL.md + run.py), видны из MCP и агентам |
| `knowledge` | база знаний: MD-блоки + frontmatter, категории, теги, версии, генерация блоков агентами |
| `library` | источники (book/video/web), главы, jobs обработки, загрузка PDF; LLM-куратор `structure_curator` чистит структуру книги (мусорные закладки → описание, номера глав книги, секции, страницы) |
| `learning` | активности («идём по источнику»), сессии-уроки со стейт-машиной theory→check→practice→debrief→done |
| `chat` | **единый вход** root-оркестратора: претрекер контента, интенты сценариев, субагенты, SSE, авто-заголовки, сжатие истории (legacy-режимы для старых разговоров) |
| `courses` | курсы-подборки, планировщик курса |
| `search` | FTS5 (блоки + главы), обновление по событиям |
| `export` | выгрузка в MD/ZIP (Obsidian-совместимая) |
| `review` | повторения SM-2, вопрос дня, очередь «дозакрепить» |
| `messenger` | Telegram-мост: отправка блоков/глав, разметка → HTML |
| `tuning` | правка промптов агентов из чата с диффом и апрувом (override в `data/prompts/`) |

**Слои внутри модуля** (проверяется import-linter, 3 контракта):
`domain` (чистая логика) → `service` (use-cases) → `infra` (SQLite-репозитории) + `api` (REST) / `tools` (MCP+агентам). Межмодульно — только публичные сервисы; события через `kernel.events.EventBus` (например, `SourceProcessed`/`SourceDeleted` → переиндексация поиска).

**Хранение**: SQLite (+FTS5) в `data/`, блоки — MD-файлы в `kb/`, миграции — Alembic (`server/migrations/`). Контекст LLM бережём: книги читаются по главам порциями (`read_chapter` offset/limit).

**LLM и агенты** (`app/llm`, `app/agent`): ModelRouter с ролями, OpenAI-совместимый провайдер (стрим, tool calls, structured output, цепочка ключей: основной `ZAI_API_KEY` + опциональные `ZAI_API_KEY_2..4` из `api_key_envs` в `server/config/llm.yaml` — при исчерпании квоты ключ уходит в cooldown ~10 мин и запрос идёт следующим), рантайм-цикл «модель → инструменты → модель» с отменой, офлоадом инструментов и трейсами в `agent_runs`; субагенты `run_agent`/`list_agents` со связкой parent_run_id. Агенты — declarative-спеки с промптами в `modules/<mod>/agents/*/prompt.md`: корневой оркестратор **root** (дефолт новых разговоров), тьюторы чата (free_chat, quick_reviewer, session_tutor), repo_scout, auditor (ревизия кода) (idea-scout: идеи из GitHub-репозиториев → data/ideas + Telegram), генераторы блоков (block_writer, categorizer, chapter_summarizer, source_overviewer), review_examiner, prompt_tuner.

**Протоколы**:
- REST `/api/*` — CRUD + SSE чата (`POST /api/conversations/{uid}/messages`: события delta/tool_start/tool_end/card/session/title/done; `research:true` — ресёрч-режим, директива уходит агенту, в чате видна только тема).
- MCP: `/mcp` (~71 инструмент) и `/mcp/<module>`.
- Действия над ссылками в чате (T-042): у YouTube/PDF-ссылок поповер «Открыть/В источники/Быстрый разбор» (новый разговор по интенту); `POST /api/sources/from-url` качает и добавляет материал (SSRF-защита). Карточки UI (command/question/evaluation/block_saved/block_updated/prompt_change/note_draft/subagent_result/attachment/action_offer/git_change) приходят инструментами через `_card`.

## Архитектура веба

Next.js App Router, TS strict, Tailwind + shadcn-подход, PWA. Дизайн-система: три темы (пергамент — по умолчанию, тёмная, светлая), иконки Material Symbols Rounded, шрифты Inter/Literata — [web/DESIGN.md](web/DESIGN.md). Серверные страницы тянут данные через `web/src/lib/api.ts`, чат — SSE (`lib/chat/stream.ts`), markdown с mermaid-рендером и авто-починкой битых схем (`components/markdown/Mermaid.tsx`). Общие подписи/эмодзи режимов и типов источников — `lib/format.ts`. Типы — рукописные в `lib/types.ts` (единственный источник правды).

Ключевые сценарии UI: мастер изучения (книга/видео → карта глав → разбор/сессия), чат с чипами инструментов и карточками (включая превью конспекта с апрувом), читалка главы с историей разговоров по главе и режимом «чистый PDF» (встроенный pdf.js-просмотрщик: переход к странице главы, ленивый рендер; полноэкранный ридер `/library/[uid]/read` с оглавлением, секциями-подпунктами, яркостью и клавиатурой) — главы показываются номерами книги («Глава 3 · Ветвление»), в markdown-читалке рендерятся картинки глав (PNG из PDF, `/api/sources/{ref}/images`), библиотека, база знаний (категории/версии/входящие), курсы, настройки. Любой материал (источник, курс, разговор, блок БЗ, активность) удаляется с диалогом подтверждения — сервер блокирует удаление при живых зависимостях (блок в курсе, сессия с блоком БЗ).

## Развертывание (прод)

- **CT 132 `learnos`** на Proxmox (4c/6G/30G SSD256, docker compose внутри): web `:3000`, api `:8765`.
- **Разработка = git push**: systemd-таймер на CT раз в 2 мин проверяет `origin/main`; есть новые коммиты → build → up → health. Логи: `journalctl -u learnos-deploy.service`, `/var/log/learnos-deploy.log`.
- Данные прода: `/opt/learnos/{data,kb}` (в git не попадают). Ключи: `ZAI_API_KEY` и опциональные `ZAI_API_KEY_2..4` (цепочка фейловера по квоте, в том же порядке, что `api_key_envs` в llm.yaml), GitHub-токен — файлами через `sec exec` (см. `proxmox/scripts/deploy/deploy-learnos-container.sh`).
- Роут: `learn.not-user-1984.duckdns.org` (NPM/hginx, wildcard-сертификат). Доступ по LAN `http://192.168.0.132:3000`; снаружи — см. задачу T-002.
- YouTube-скилл ходит через хомлаб-прокси `socks5://192.168.0.10:1080` (vpn-gw).
- ⚠️ Сон сервера 19:00–08:30; ⚠️ стоп-случай: доступ с мобилки вне дома пока не настроен.

## Воркфлоу разработки

Полные правила — [task_ai/tasks/README.md](task_ai/tasks/README.md) и [AGENTS.md](AGENTS.md). Кратко:

1. Задача из `task_ai/tasks/` (status: active) или от пользователя → файл-задача.
2. Код по правилам `task_ai/07-code-standards.md`: русские docstring, слои, модульность, новое поведение = тесты.
3. Все проверки зелёные (server: ruff/format/pytest/import-linter; web: eslint/tsc/build).
4. Коммит (одно изменение = один коммит) → push → автодеплой → health/prod проверен.
5. **После успешного деплоя**: задача в `task_ai/archive/` + строка в `archive/README.md`, документация (README/ARCHITECTURE/AGENTS) обновлена.

Референсы агентных решений: [task_ai/hermes-ideas.md](task_ai/hermes-ideas.md) (конспект из nousresearch/hermes-agent).

## Карта документации

- [AGENTS.md](AGENTS.md) — правила для агентов, запуск, эндпоинты, текущий статус
- [ARCHITECTURE.md](ARCHITECTURE.md) — компоненты, модель данных, MCP-инструменты, стейт-машина сессии
- [PLAN.md](PLAN.md) — видение, фазы, зафиксированные решения
- [task_ai/README.md](task_ai/README.md) — ТЗ: справочники 01–08, этапы, приоритеты
- [task_ai/tasks/README.md](task_ai/tasks/README.md) — система задач агента-разработчика
- [task_ai/archive/README.md](task_ai/archive/README.md) — история выполненного
- [web/DESIGN.md](web/DESIGN.md) — дизайн-система веба: темы, иконки, шрифты, токены
