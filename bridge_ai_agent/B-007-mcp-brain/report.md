# B-007 — отчёт исполнителя

## Изменённые файлы

**Новый модуль brain:**
- `server/app/modules/brain/service.py` — `capture` (text→inbox-заметка с дедупом по sha256 нормализованного текста — хэш живёт тегом блока; url→источник с дедупом + запуск обработки), `context` (FTS + inbox-матчинг словами, ранжирование verified→главы→inbox, excerpt по предложениям, budget_chars, next_cursor), `get` (пачка blk_…/src_…/src_…:N), `list_topics`, `inbox`, `promote_hint`, `add_source`
- `server/app/modules/brain/tools.py` — 8 тулов с описаниями всех параметров (capture, context, search_kb, get, list_topics, add_source_kb, inbox, promote_hint)
- `server/app/modules/brain/__init__.py` + регистрация в `bootstrap.py` (17 модулей, 84 тулов)

**Сервер, смежные правки:**
- `kernel/tools/mcp_adapter.py` — inputSchema теперь несёт description/default/constraints: сигнатуры генерируются с `Annotated[тип, FieldInfo]`; default_factory материализуется дефолтом (ограничение синтаксиса Python); `deprecated` в ToolSpec → пометка «[УСТАРЕЛО: …]» в tools/list; `build_mcp_server(instructions=, resources=)`
- `kernel/tools/spec.py` — поле `deprecated`
- `main.py` — `/mcp/brain` с instructions (capture→context→get, inbox≠выученное) и ресурсами-шаблонами `learnos://block/{uid}`, `learnos://source/{uid}/chapter/{idx}`; инструкции общему `/mcp`
- `modules/knowledge/tools.py` — `save_note` канальный дефолт (B-007): канал `agent` (веб-чат после апрува превью) → confirmed/verified; внешний MCP → inbox/unverified
- `modules/knowledge/infra/sql_repo.py` — inbox-фильтр: category_status IN (suggested, inbox)
- `modules/library/service.py` + `domain.py` + `infra/sql_repo.py` — `add_source` дедуп по нормализованному URL (`normalize_url`: без фрагмента/хвостового слэша), ответ несёт `created`; `SourceRepository.find_by_url`
- Описания параметров проставлены во ВСЕХ tools.py модулей (knowledge, learning, library, courses, chat, export, messenger, research, review, revision, search, tuning) — 0 полей без description (проверено скриптом)
- `search/tools.py` — `search_chunks` помечен deprecated; `skills/web-search/SKILL.md` — пометка в description
- `tests/contract/test_registry.py` — brain в MCP_MODULES; `tests/unit/preview_note_test.py` — FakeKnowledge поддержал verified

**Документация:** `README.md` — раздел «Подключить LearnOS как мозг к Claude Code / opencode» (конфиг MCP с bearer из env, список тулов, идемпотентность).

**Тесты:** `tests/api/test_brain.py` — capture text/url идемпотентны; context в бюджете и verified раньше inbox; save_note из MCP → inbox / из agent → confirmed; **e2e MCP SDK-клиентом** (ASGI-транспорт + lifespan): initialize, tools/list (8 тулов, у capture параметры с description), capture×2, context, read_resource.

## Результаты проверок

- `cd server`: ruff ✅ · format ✅ · lint-imports ✅ (4/4) · pytest ✅ (весь suite + e2e; кроме 4 предсуществующих сетевых test_from_url)
- `cd web`: не менялся (REST-схема не тронута — gen:api не нужен)

## Отклонения и решения

1. **Имена двух тулов переименованы против плана**: `search`→`search_kb`, `add_source`→`add_source_kb` — глобальный реестр требует уникальные имена, `search`/`add_source` уже заняты модулями search/library. Остальные 6 — как в плане.
2. **`save_note` confirm-флаг не добавлял**: подтверждение определяется каналом (agent=веб-чат после апрува превью — confirmed, как раньше; mcp — inbox). Промпты агентов не пришлось править — поведение веб-чата сохранено, риск из плана снят архитектурно.
3. **default_factory в MCP-схеме** материализуется значением фабрики (list→`[]`): pydantic не принимает default+default_factory вместе, а Python — параметр без дефолта после дефолтных. Описание поля сохраняется.
4. **inbox-дедуп текста через тег** `sha256:<16>` — индексируется существующим block_tags, без новой колонки/миграции.
5. **Прод-смоук tools/list на /mcp/brain** — не выполнял (пуша не было по правилам задачи); e2e-тест покрывает тот же путь. Сделать после деплоя.

## Вопросы

- Нет блокеров.
