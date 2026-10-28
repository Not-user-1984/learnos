# LearnOS — архитектура (v2, модульный монолит)

> Полное ТЗ — в [task_ai/](task_ai/): [02-архитектура](task_ai/02-architecture.md), [03-модель данных](task_ai/03-data-model.md), [04-API/MCP](task_ai/04-api-and-mcp.md), [05-LLM/агенты](task_ai/05-llm-and-agents.md), [06-UI](task_ai/06-ui.md). Здесь — краткая карта текущей реализации.

## Стек

- **Ядро** `server/` — Python 3.12, FastAPI, SQLAlchemy 2 (Core), Alembic, MCP (streamable HTTP), z.ai GLM через OpenAI-совместимый слой с **цепочкой ключей** (`ZAI_API_KEY`, опционально `ZAI_API_KEY_2..4` — ротация при квоте). Слои: domain → ports/application → infrastructure; связывает `bootstrap.py` (Container + список модулей).
- **Веб** `web/` — Next.js App Router, TS strict, SSE-чат.
- **Прод** — CT 132, docker compose; рабочая копия репо смонтирована read-only в `/repo` для аудитора.

## Модули (`server/app/modules/`) — 15

| Модуль | Что делает | Агенты |
|---|---|---|
| profile | машины и предпочтения (`settings.profile`) | — |
| skills | скиллы: builtin `server/skills/*` + агентские `data/agent-skills/<agent>/*` (subprocess-песочница, save_skill с горячей перезагрузкой) | — |
| knowledge | блоки (MD в `kb/blocks/` + индекс), категории, версии, reindex | block_writer, categorizer, runbook_writer |
| library | источники (PDF/YouTube/веб), главы, jobs + воркер | chapter_summarizer, source_overviewer, structure_curator |
| learning | активности, сессии (стейт-машина theory→check→practice→debrief), практика | — |
| chat | **единый вход** (root-оркестратор), разговоры, SSE, претрекер контента (YouTube/URL/arXiv/DOI), вложения, интенты | root, free_chat, quick_reviewer, session_tutor, repo_scout |
| courses | подборки с прогрессом и «следующим шагом» | course_planner |
| search | FTS5 (blocks_fts, chapters_fts), обновление по событиям | — |
| export | MD/ZIP выгрузки (Obsidian-friendly) | — |
| review | повторения (SM-2), очередь слабых мест, Telegram-дайджесты | review_examiner |
| messenger | Telegram-шлюз (блоки/главы/тексты) | — |
| tuning | промпты и агенты: оверрайды `data/prompts`, кастомные агенты, propose_change (prompt\|skill) | prompt_tuner, agent_designer |
| mcpext | сторонние MCP-серверы → обёртки инструментов | mcp_designer |
| research | поиск (цепочка провайдеров, academic-агрегат, youtube), идея-скаут | — |
| revision | ревизия кода: read-only доступ к репо, задачи, git-ветки `agent/*` через worktree с guard-листом | auditor |

Сквозные слои: `kernel` (config/db/errors/events/tools), `llm` (провайдеры + ModelRouter по ролям из `config/llm.yaml`), `agent` (AgentRuntime с субагентами `run_agent`, трейсы `agent_runs` c `parent_run_id`).

## Ключевые потоки

- **Оркестратор (эпик T-034)**: `/chat` — один вход; новый разговор всегда root. Претрекер распознаёт контент сообщения без LLM (заметка в system_extra с готовыми действиями), root сам отвечает на простое и зовёт субагентов `run_agent` (каталог `list_agents`); предложения — карточками `action_offer`. Сценарии входа — интентами (`review/study/session/quote/tune/reinforce` с первым сообщением → директива агенту). Legacy-режимы free/quick/session/tuning/`agent:<name>` живут для старых разговоров и MCP.
- **Песочница скиллов**: агент создаёт скилл `save_skill` → `data/agent-skills/<agent>/<skill>/` → исполняется subprocess (раннер, таймаут, лимит записи в data/) → доступен сразу (горячая перезагрузка реестров). Правки builtin-скиллов/промптов — карточкой `propose_change` с бэкапом и откатом.
- **Ревизия кода**: auditor читает `/repo` (секреты `.env/.pem/.key` недоступны), создаёт задачи `task_ai/tasks/`; git-правки — только ветки `agent/*` в worktree, коммит с зелёными ruff/pytest, guard-лист ядра; применение — человеком (карточка `git_change`).
- **Знание рождается через диалог**: `finish_session`/`save_note` → MD-файл v2 + индекс + событие BlockSaved → search индексирует; категория `suggested` ждёт подтверждения.
- **Чат**: `POST /api/conversations/{uid}/messages` → SSE (delta/tool_start/tool_end/card/session/title/done); генерация в фоновой задаче — переживает разрыв; «Стоп» через токен отмены.
- **Обработка источника**: upload/добавление → job `process_source` (скилл) → `summarize_chapters` (LLM по главам) → обзор.

## Проверки

- Сервер: `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest` (295 тестов: unit/integration/api/contract/agent).
- Веб: `cd web && npm run lint && npx tsc --noEmit && npm run build`.
- Живой LLM: `sec exec ZAI_API_KEY -- docker compose up -d`, затем `docker exec learnos-server uv run python -m app.cli smoke-llm`.
