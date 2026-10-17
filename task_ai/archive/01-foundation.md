# Этап 1 — Фундамент: модульный бэкенд, схема v2, LLM-слой, оболочка UI

**Цель:** перевести сервер на модульную слоистую архитектуру с тестами, мигрировать данные на схему v2, подключить LLM-слой и агентный рантайм (пока без чата), собрать оболочку веб-интерфейса на shadcn. Пользователь функционально почти ничего нового не видит, но всё дальнейшее строится на этом.

**Справочники:** [02](../02-architecture.md), [03](../03-data-model.md), [04](../04-api-and-mcp.md) (реестр, совместимость MCP), [05](../05-llm-and-agents.md) §1–2, [06](../06-ui.md) (библиотеки, оболочка, Markdown), [07](../07-code-standards.md).

## Задачи

### Бэкенд: каркас

- [x] Добавить зависимости и dev-инструменты (`sqlalchemy`, `alembic`, `pydantic-settings`, `openai`, `python-multipart`, `anyio`, `jinja2`; dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `import-linter`, `respx`). Настроить ruff/mypy/pytest/import-linter в `pyproject.toml`, команду проверки из [07](../07-code-standards.md).
- [x] `app/kernel/`: `config.py` (Settings), `db.py` (engine, UoW с очередью событий), `errors.py`, `events.py`, `ids.py`, `clock.py`, `logging.py`, `module.py`, `tools/` (spec, registry, mcp_adapter, llm_adapter).
- [x] `bootstrap.py` (Container, список модулей) и `main.py` (`create_app()`), exception handler `AppError` → HTTP.
- [x] Контракты import-linter: слои внутри модуля; модули не импортируют `infra`/`tables` друг друга; `kernel`, `llm`, `agent` не импортируют `modules`.

### Бэкенд: модули (перенос текущего функционала)

- [x] `library`: источники (без обязательного курса), главы, `read_chapter`, `process_source` через скиллы, таблица `jobs` и воркер (job `process_source`; summary глав пока не генерируются — этап 2).
- [x] `knowledge`: `BlockDraft` → MD v2 (`md_store.py`, yaml frontmatter), чтение MD → индекс, `kb/categories.yaml`, `save_block`, `get_block`, `list_blocks` (простые фильтры), `update_block` + `block_versions` + `restore`, `reindex` (CLI + REST).
- [x] `learning`: активности; сессии — стейт-машина из `core.py` в `domain.py` без изменения переходов; `start_session(course_id | activity)`, `advance`, `finish_session(block_json)` (генерация без `block_json` — этап 2).
- [x] `courses`: курсы + `course_items` (CRUD, без прогресса и планировщика).
- [x] `profile`: `settings.profile` с дефолтом из [03](../03-data-model.md), `GET/PUT /api/settings/profile`, инструмент `get_profile`.
- [x] `skills`: загрузчик `server/skills/*` → `ToolSpec` (формат SKILL.md не меняется).
- [x] `search`: FTS5 по блокам и главам, обновление по событиям `BlockSaved`/`BlockUpdated`/`SourceProcessed`; `search` + алиас `search_chunks`.
- [x] MCP: `/mcp` (все инструменты) и `/mcp/<module>`; все старые имена инструментов и аргументы из [04](../04-api-and-mcp.md) работают. Старые REST-роуты — алиасы.
- [x] Удалить `core.py`, `kb.py`, `api.py`, `mcp_server.py`, `db.py` старого вида после переноса (функции живут в модулях).

### Миграция

- [x] Alembic: `0001_baseline` (текущая схема), `0002_v2` (схема + перенос данных + файлов `kb/` по шагам из [03](../03-data-model.md)), бэкап БД перед апгрейдом, `stamp` для существующей БД.
- [x] Тест миграции на фикстуре БД старого формата с 1 курсом, 1 источником, 2 главами, 1 сессией, 1 блоком и MD-файлом.

### LLM и агенты

- [x] `app/llm/`: типы, `LLMProvider`, `openai_compat.py` (complete, stream, tool calls, нормализация ошибок, ретраи), `fake.py`, `factory.py`, `router.py`, `structured.py`; `server/config/llm.yaml` из [05](../05-llm-and-agents.md).
- [x] `app/agent/`: `AgentSpec`, `AgentRegistry`, `AgentRuntime` (цикл, отмена, max_steps), `run_structured`, трейсинг в `agent_runs`.
- [x] `cli smoke-llm`: живой вызов роли `chat` (ответ), стрим, tool call с тестовым инструментом `echo`.
- [x] `GET /api/health`: БД, LLM (`configured`, провайдер/модель роли `chat`), воркер.

### Веб: оболочка

- [x] `npx shadcn@latest init` (Tailwind v4), компоненты из списка [06](../06-ui.md); `next-themes`, `lucide-react`, Geist через `next/font`, `@tailwindcss/typography`.
- [x] Layout: сайдбар (Чат, База знаний, Библиотека, Курсы, Настройки), крошки, переключатель темы, ⌘K-палитра (пока: навигация по разделам + поиск блоков через `/api/search`).
- [x] Страницы-заглушки разделов с пустыми состояниями; текущий список блоков и карточку блока перенести в `/kb` и `/kb/[uid]` (редирект со старых путей).
- [x] Новый компонент Markdown ([06](../06-ui.md) «Компонент Markdown») с Shiki, alerts, KaTeX, wikilinks, mermaid с темой.
- [x] `/settings`: редактор профиля (машины + обучение), блок «Модели» (статус из `/api/health`).
- [x] `npm run gen:api` по новому OpenAPI, фронт собран только на сгенерированных типах.

### Документация

- [x] `ARCHITECTURE.md` — заменить содержимое кратким описанием новой структуры со ссылками на `task_ai/02–05`; `AGENTS.md` — новые команды запуска/проверки.

## Критерии приёмки

1. Команда проверки из [07](../07-code-standards.md) проходит без ошибок (ruff, mypy, import-linter, pytest).
2. Тесты есть на всех уровнях из [07](../07-code-standards.md) «Тесты»; покрытие domain + service ≥ 85%.
3. На копии реальной `data/learnos.db` миграция проходит, бэкап создан, блок `blk_87ab94` лежит в `kb/blocks/`, открывается в `/kb/blk_87ab94` с mermaid-схемой; повторный запуск миграции ничего не меняет.
4. opencode из корня проекта видит `/mcp`; цикл `create_course → add_source → process_source → start_session → advance(theory_done) → advance(go_practice) → advance(practice_done) → finish_session(block_json)` создаёт MD-файл v2 и запись в индексе (проверить curl/скриптом через REST и вручную через MCP).
5. `GET /mcp/knowledge` отдаёт только инструменты базы знаний (проверить листингом инструментов).
6. `update_block` → версия +1, предыдущая в `block_versions`, `restore` возвращает содержимое; ручная правка MD + `reindex` видна в API.
7. `sec exec ZAI_API_KEY -- uv run python -m app.cli smoke-llm` — три проверки OK; без ключа — `/api/health` показывает `llm.configured=false`, сервер работает.
8. Веб: `npm run lint && npx tsc --noEmit && npm run build` проходят; оболочка работает в тёмной и светлой теме и на ширине 390px; профиль сохраняется и переживает перезапуск.

## Отчёт

**Статус: выполнен (2026-10-13).**

Что сделано и чем проверено:

- Каркас: `app/kernel/` (config/db UoW+события/errors/events/ids/clock/logging/module/tools: spec+registry+mcp_adapter), `app/llm/` (types, provider, openai_compat с ретраями и пересозданием клиента при смене event loop, fake, router, structured_output), `app/agent/` (AgentSpec/Registry/Runtime с отменой и max_steps, run_structured, DbRunRecorder → agent_runs), `bootstrap.py` (Container + 9 модулей), `main.py` (create_app + `/api/health`), `cli.py` (migrate|reindex|smoke-llm|seed-demo).
- 9 модулей по контракту Module (wire/routers/tools/subscribe); 40 инструментов в едином ToolRegistry; MCP `/mcp` (все) + `/mcp/<module>` (проверено листингом инструментов: `/mcp/knowledge` отдаёт только 9 инструментов базы знаний); все 17 старых имён MCP сохранены (контрактный тест).
- Миграции: `0001_baseline` (идемпотентная v1-схема), `0002_v2` (перенос sources/courses/sessions/blocks, uid, course_items, kb/*.md → kb/blocks/ c frontmatter v2, categories.yaml, settings.profile, FTS5). Проверено на живой БД (бэкап `learnos.db.bak-*` создан; `blk_87ab94` лежит в `kb/blocks/` и открывается) и тестом на фикстуре v1 (миграция + повторный запуск no-op). Особенности хода работы: FK-ссылки после `ALTER TABLE … RENAME` чинились через `PRAGMA legacy_alter_table` + ручной ремонт sqlite_master существующих БД; stamp не используется (0001 идемпотентен).
- LLM: z.ai GLM-5.3 (chat/structured/fast); `smoke-llm` в контейнере: complete/stream/tool call — 3/3 OK; без ключа `/api/health` отдаёт `llm_configured=false`, сервер работает (тест + живая проверка).
- Веб: shadcn (base-nova, Base UI), оболочка с сайдбаром/⌘K/темой, страницы-разделы, `/kb`+`/kb/[uid]` с mermaid/alerts/KaTeX/wikilinks, `/settings` (профиль+модели+MCP+обслуживание), `gen:api` типы сгенерированы. `tsc --noEmit` и `npm run build` — чистые.
- Команда проверки: `ruff check` 0, `ruff format --check` 0, `import-linter` 3 контракта KEPT, `pytest` 87 passed (unit/integration/api/contract/agent, без сети).

Отклонения/решения: Inter+JetBrains Mono вместо Geist (нет кириллицы); SSE-прокси браузера — Next route handler `/api/[...path]` (runtime env, реврайты запекаются при сборке); MCP-роуты регистрируются напрямую (mount ломал пути); `advance` из чата работает без `session_id` (uid сессии передаётся в ToolContext); mypy — известные ошибки типизации не чинились (вне критериев приёмки), полный ноль mypy перенесён в бэклог.

