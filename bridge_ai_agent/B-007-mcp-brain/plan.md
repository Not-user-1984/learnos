# B-007 · MCP «второй мозг»: capture и context за один вызов, inbox, idempotency, описания

Цель: внешняя нейронка (Claude Code, opencode) через MCP одним вызовом кладёт материал в LearnOS и одним
вызовом получает компактный контекст по теме. Правило «выученное = только через сессию» сохраняется:
всё от нейронок попадает во входящие как непроверенное.
Контекст: `docs/system-review-2026-11.md` §4.

## Готово, когда
- [ ] Есть компактный эндпоинт `/mcp/brain` с ≤8 инструментами: `capture`, `context`, `search`, `get`,
      `list_topics`, `add_source`, `inbox`, `promote_hint`.
- [ ] `capture` идемпотентен: повтор того же контента/URL возвращает существующую запись (`created=false`).
- [ ] `context(topic, budget_chars)` за 1 вызов отдаёт блоки + фрагменты глав + заметки inbox, укладываясь в бюджет,
      с пометкой verified/inbox и ссылками-uid для `get`.
- [ ] `save_note` по умолчанию пишет во входящие (`category_status="inbox"`, `verified=false`); прямое confirmed —
      только с явным флагом и только из веб-чата пользователя (не из внешнего MCP).
- [ ] У всех тулов MCP параметры с описаниями (видно в `tools/list`); у сервера осмысленные instructions.
- [ ] Ресурсы MCP: `learnos://block/{uid}`, `learnos://source/{uid}/chapter/{idx}`.
- [ ] Дубли помечены deprecated в описании (`search_chunks`, скилл `web-search`), не удалены.
- [ ] Проверки зелёные; e2e-тест MCP-клиентом.

## Контекст в коде
- `server/app/kernel/tools/mcp_adapter.py:45` — только `add_tool`; монтирование `server/app/main.py:272-293`.
- `server/app/modules/knowledge/tools.py` — `save_note` (~91-135, confirmed ~31-48), inbox в `knowledge/service.py:231`.
- `server/app/modules/search/tools.py:37` — FTS5 `search`.
- `server/app/modules/library/service.py:95` — `add_source` без дедупа.
- `server/app/modules/export/tools.py:27` — пример лимита `max_chars` + `truncated`.

## Изменения
1. **Новый модуль `modules/brain/`** (api не нужен, только tools + service), использует сервисы knowledge/library/
   search через контейнер (не infra).
   - `capture(kind: text|url|file_path, content, title?, topic?, tags?, source_agent?)` →
     text → заметка-блок `kind="note"`, inbox, `verified=false`, `meta.captured_by=source_agent`;
     url → `add_source` (YouTube/PDF/web) + постановка обработки; дедуп: url — нормализованный URL,
     text — sha256 нормализованного текста (хранить хэш в метаданных блока, индекс).
     Ответ: `{uid, kind, created: bool, status}`.
   - `context(topic, budget_chars=8000, include=[blocks,chapters,inbox])` → поиск (FTS сейчас, гибрид после B-008),
     ранжирование: verified блоки → главы → inbox; каждый элемент `{uid, type, title, verified, excerpt}`;
     `truncated`, `next_cursor`. Excerpt режется по предложениям.
   - `get(uids: list[str], max_chars_each=4000)` — batch для блоков/глав/источников.
   - `list_topics()` — дерево категорий с числом блоков.
   - `inbox(limit)` — что ждёт разбора.
   - `promote_hint(uid)` — не превращает в verified, а возвращает подсказку: «проведи сессию по этому, ссылка».
2. **knowledge**: `save_note` default → inbox/unverified; флаг `confirm=true` разрешён только из канала веб-чата
   (канал передаётся в контексте вызова тула; если в рантайме канала нет — добавить поле в контекст ToolSpec).
3. **library**: `add_source` — дедуп по нормализованному URL (вернуть существующий, `created=false`).
4. **kernel/tools**: в `mcp_adapter` пробрасывать `Field(description=…)` в JSON-схему (проверить, что pydantic
   `model_json_schema()` уходит в `inputSchema`); пройтись по всем tools.py и дописать `description` полям
   (коротко, по-русски); добавить поддержку ресурсов (`ResourceSpec` в реестре → `add_resource`).
   Instructions сервера: 5–8 строк «как пользоваться LearnOS: capture → context → get; выученное = verified».
5. **main.py**: смонтировать `/mcp/brain`.
6. **Документация**: раздел в `README.md` «Подключить LearnOS как мозг к Claude Code / opencode» с примером
   конфигурации MCP (URL + bearer из env, без значения токена).

## Тесты
- capture text дважды → один блок; capture url дважды → один источник.
- context укладывается в budget, verified идут раньше inbox.
- save_note из MCP → inbox; из веб-канала с confirm → confirmed.
- e2e: MCP-клиент SDK на тестовом приложении вызывает `tools/list` (`/mcp/brain` ≤8 тулов, у параметров есть description),
  `capture`, `context`, `resources/read`.

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- Прод-смоук после деплоя: `sec exec LEARNOS_API_TOKEN -- …` вызов `tools/list` на `/mcp/brain` (токен не печатать).

## Риски
- Изменение дефолта `save_note` меняет поведение агентов веб-чата: проверить промпты агентов, которые зовут
  `save_note` (`grep -rn save_note server/app/modules/*/agents`), и где пользователь явно просил «запиши в базу» —
  передавать confirm.
- Inbox-блоки не должны считаться выученными в курсах (B-004 смотрит только verified).
