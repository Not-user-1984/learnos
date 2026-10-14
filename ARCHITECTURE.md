# LearnOS — архитектура (v2, модульный монолит)

Полное ТЗ — в [task_ai/](task_ai/): [02-архитектура](task_ai/02-architecture.md), [03-модель данных](task_ai/03-data-model.md), [04-API/MCP](task_ai/04-api-and-mcp.md), [05-LLM/агенты](task_ai/05-llm-and-agents.md), [06-UI](task_ai/06-ui.md). Здесь — краткая карта текущей реализации.

## Стек

- **Ядро** `server/` — Python 3.12, FastAPI, SQLAlchemy 2 (Core), Alembic, MCP (streamable HTTP), z.ai GLM через OpenAI-совместимый слой. Слои: domain → ports/application → infrastructure; связывает `bootstrap.py` (Container + список модулей).
- **Веб** `web/` — Next.js 16 (App Router), React 19, TS strict, Tailwind v4 + shadcn (Base UI), mermaid/KaTeX/alerts; типы из OpenAPI (`npm run gen:api`); клиентские запросы — через runtime-прокси `/api/*` (route handler → `LEARNOS_API_URL`).
- **Docker** — `docker compose up -d`: `server` (8765: REST + MCP `/mcp` и `/mcp/<module>`) + `web` (3000, standalone); тома `./data` и `./kb`.

## Модули (`server/app/modules/`)

| Модуль | Что делает | Агенты |
|---|---|---|
| profile | машины и предпочтения (`settings.profile`) | — |
| skills | drop-in скиллы `server/skills/*` → ToolSpec | — |
| knowledge | блоки (MD в `kb/blocks/` + индекс), категории, версии, reindex | block_writer, categorizer |
| library | источники (PDF/YouTube), главы, jobs + воркер | chapter_summarizer |
| learning | активности, сессии (стейт-машина theory→check→practice→debrief), практика | — |
| chat | разговоры, сообщения, SSE, контекст-билдер | free_chat, quick_reviewer, session_tutor |
| courses | подборки с прогрессом и «следующим шагом» | course_planner |
| search | FTS5 (blocks_fts, chapters_fts), обновление по событиям | — |
| export | MD/ZIP выгрузки (Obsidian-friendly) | — |

Сквозные слои: `kernel` (config/db/errors/events/tools), `llm` (провайдеры + ModelRouter по ролям из `config/llm.yaml`), `agent` (AgentRuntime + трейсы в `agent_runs`).

## Ключевые потоки

- **Знание рождается через диалог**: `finish_session`/`save_note` (с явным драфтом или генерацией block_writer'ом из транскрипта/переписки) → MD-файл v2 + индекс + событие BlockSaved → search индексирует, категория `suggested` ждёт подтверждения во «Входящих».
- **Чат**: `POST /api/conversations/{uid}/messages` → SSE (delta/tool_start/tool_end/card/session/title/done); генерация в фоновой задаче — переживает разрыв соединения; «Стоп» через токен отмены.
- **Обработка источника**: upload/добавление → job `process_source` (скилл) → job `summarize_chapters` (LLM по главам) → обзор источника.

## Проверки

- Сервер: `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest` (87 тестов: unit/integration/api/contract/agent).
- Веб: `cd web && npm run lint && npx tsc --noEmit && npm run build`.
- Живой LLM: `sec exec ZAI_API_KEY -- docker compose up -d`, затем `docker exec learnos-server uv run python -m app.cli smoke-llm`.
