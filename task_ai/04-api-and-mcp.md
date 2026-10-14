# 04 — REST, SSE-чат, MCP

Все REST-ответы — JSON. Ошибки: HTTP 4xx/5xx + `{"error": "code", "message": "человекочитаемо"}`. Pydantic-модели ответов объявлены явно (`response_model`), чтобы `npm run gen:api` давал точные типы фронту.

## Реестр инструментов

Инструменты объявляются в `modules/<m>/tools.py` и отдаются модулем через `Module.tools()` (см. [02-architecture.md](02-architecture.md)).

```python
def library_tools(c: Container) -> list[ToolSpec]:
    """Инструменты модуля «Библиотека»."""
    svc = c.library

    def read_chapter(args: ReadChapterArgs, ctx: ToolContext) -> ChapterTextDTO:
        """Отдаёт порцию текста главы, чтобы не грузить источник целиком."""
        return svc.read_chapter(args.source_id, args.chapter, args.offset, args.limit)

    return [
        ToolSpec(
            name="read_chapter",
            module="library",
            description="Текст главы порционно: offset/next_offset. Не грузи весь источник.",
            args_model=ReadChapterArgs,
            handler=read_chapter,
            channels={"mcp", "agent"},
            modes={"free", "quick", "session"},
        ),
    ]
```

- Аргументы — pydantic-модель → из неё JSON Schema для MCP и для описаний инструментов LLM.
- Обработчик возвращает pydantic-DTO или dict. `AppError` адаптеры превращают в `{"error": code, "message": ...}`.
- Имена инструментов уникальны глобально; дубликат при сборке реестра — ошибка старта.
- Для агента: результат обрезается до `LEARNOS_TOOL_RESULT_MAX_CHARS` (по умолчанию 8000) с пометкой `"truncated": true`.
- Скиллы из `server/skills/` регистрируются в реестре автоматически (как сейчас в MCP) с `channels={"mcp","agent"}`.
- Инструмент может вернуть ключ `_card` — карточку UI (см. «Карточки»); в LLM она не уходит, в SSE — уходит.

## MCP-инструменты v2

Ниже — инструменты этапов 1–2 и правила совместимости. **Полный каталог по всем этапам, уровни доступа, промпты и ресурсы — [08-mcp-parity.md](08-mcp-parity.md); при расхождении прав он.**

Эндпоинты: `/mcp` — все инструменты (подключён в `opencode.json`); `/mcp/<module>` — только инструменты модуля (`/mcp/knowledge`, `/mcp/library`, `/mcp/learning`, …).

Совместимость: существующие имена и аргументы (`start_session(course_id)`, `advance`, `finish_session(session_id, block_json)`, `list_blocks(course_id?)`, `get_block`, `read_chapter`, `list_chapters`, `process_source`, `add_source(course_id, …)`, `research_sources`, `search_chunks`, `list_skills`, `run_skill`) продолжают работать. Новые аргументы — только опциональные. `course_id` в `add_source` становится опциональным (если задан — источник добавляется в курс).

| Группа | Инструмент | Аргументы | Назначение |
|---|---|---|---|
| Источники | `add_source` | kind, title, url?, local_path?, course_id? | добавить в библиотеку |
| | `list_sources` | kind?, q?, course_id? | список |
| | `get_source` | source (uid или id) | обзор + главы (title, summary, key_points) |
| | `process_source` | source_id | запускает job, возвращает `job_id` |
| | `get_job` | job_id | статус/прогресс |
| | `list_chapters` / `read_chapter` | как сейчас | |
| | `research_sources` | topic, limit? | веб-поиск кандидатов |
| Поиск | `search` | q, scope: blocks\|chapters\|all, limit? | FTS5 по блокам и главам |
| | `search_chunks` | q | алиас `search(scope=chapters)` для совместимости |
| Активности | `start_activity` | source, course_id? | «идём по источнику» |
| | `list_activities` / `get_activity` | | курсор, пройденные главы, блоки |
| Сессия | `start_session` | course_id? \| activity?, chapter?, config? | одно из course_id/activity обязательно |
| | `get_session_state` / `advance` | как сейчас | |
| | `practice_step` | session_id, machine, command, explanation, expected?, risk: low\|medium\|high | пишет `practice_log` в транскрипт, отдаёт карточку команды |
| | `finish_session` | session_id, block_json? | если `block_json` пуст — сервер генерирует драфт LLM из транскрипта |
| БЗ | `save_note` | title?, draft_json?, source?, chapter?, conversation? | блок-конспект (`kind: note`); без draft — генерация из разговора |
| | `list_blocks` | category?, tag?, kind?, source?, q?, sort?, course_id? | |
| | `get_block` | block_uid | MD целиком + метаданные |
| | `update_block` | block_uid, patch_json, reason | правка сразу, предыдущая версия → `block_versions` |
| | `list_block_versions` / `restore_block_version` | block_uid, version | история и откат |
| | `list_categories` / `create_category` | path, title, color?, icon? | дерево |
| | `set_block_category` | block_uid, path, confirm: bool | агент ставит `confirm=false`; подтверждение — я в UI |
| Курсы | `create_course` | title, topic, description?, items? | |
| | `list_courses` / `get_course` | | с прогрессом |
| | `add_course_item` / `remove_course_item` / `reorder_course` | | |
| Профиль | `get_profile` | — | машины и предпочтения |
| Экспорт | `export_markdown` | scope: block\|category\|course\|source\|all, id?, max_chars? | склеенный MD (для передачи другой нейронке) |
| Скиллы | `list_skills` / `run_skill` + авто-скиллы | | как сейчас |

`patch_json` для `update_block`: частичный `BlockDraft` (см. [05-llm-and-agents.md](05-llm-and-agents.md)); списки заменяются целиком, плюс операции `append_theses`, `append_examples`, `append_concepts`, `append_weak_spots` для точечных добавлений.

## REST

Префикс `/api`. Старые роуты сохранить, новые:

```
GET    /api/health                                  -> {ok, llm_configured, model}
GET    /api/settings/profile        PUT (body Profile)
POST   /api/settings/llm-test                       -> короткий пинг модели

GET    /api/sources?kind=&q=&sort=                  -> [SourceCard] (с прогрессом)
POST   /api/sources                                 (json: kind,title,url)  — YouTube/web
POST   /api/sources/upload                          (multipart: file, title?) — PDF; сразу ставит job обработки
GET    /api/sources/{uid}                           -> SourceDetail (summary, главы, блоки по главам, активности)
POST   /api/sources/{id}/process                    -> {job_id}
GET    /api/sources/{id}/chapters                   (как сейчас)
GET    /api/sources/{id}/chapters/{idx}             (как сейчас)
GET    /api/jobs/{id}

POST   /api/activities                              {source, course_id?} -> Activity
GET    /api/activities?status=
GET    /api/activities/{uid}

GET    /api/conversations?mode=&q=                  -> [ConversationListItem]
POST   /api/conversations                           {mode, activity?, chapter?, focus_block?, title?}
GET    /api/conversations/{uid}                     -> {conversation, messages[], session?}
PATCH  /api/conversations/{uid}                     {title?}
DELETE /api/conversations/{uid}                     (сообщения удаляются, блоки — нет)
POST   /api/conversations/{uid}/messages            {content} -> text/event-stream (см. ниже)
POST   /api/conversations/{uid}/stop                прервать текущую генерацию

GET    /api/kb/blocks?category=&tag=&kind=&source=&status=&q=&sort=&order=&limit=&offset=
GET    /api/kb/blocks/{uid}                         -> Block (meta + content + versions_count)
GET    /api/kb/blocks/{uid}/versions                GET /api/kb/blocks/{uid}/versions/{v}
POST   /api/kb/blocks/{uid}/restore/{v}
POST   /api/kb/blocks/{uid}/category                {path, confirm: true}
GET    /api/kb/categories                           -> дерево с count (вкл. подкатегории)
POST   /api/kb/categories   PATCH /api/kb/categories/{path}   (title, color, icon, sort)
GET    /api/kb/tags                                 -> [{tag, count}]
GET    /api/kb/inbox                                -> блоки с category_status=suggested
POST   /api/kb/reindex
GET    /api/search?q=&scope=                        (FTS5; старый формат ответа для scope=chapters)

GET    /api/courses   POST /api/courses   GET/PATCH/DELETE /api/courses/{uid}
POST   /api/courses/{uid}/items   DELETE /api/courses/{uid}/items/{id}   POST /api/courses/{uid}/reorder

GET    /api/export?scope=&id=&format=md|zip         -> файл (Content-Disposition)
```

Старые `/api/blocks`, `/api/blocks/{uid}` — оставить как алиасы `/api/kb/blocks…`.

Сортировки блоков `sort`: `created` (по умолчанию, desc), `updated`, `title`, `source`, `weak` (больше «дозакрепить» — выше).
`status`: `inbox` (категория не подтверждена), `weak` (есть «дозакрепить»), `lesson`, `note`.

## SSE-протокол чата

`POST /api/conversations/{uid}/messages` → `Content-Type: text/event-stream`. Каждое событие — `event: <type>\ndata: <json>\n\n`. Фронт читает через `fetch` + `ReadableStream` (EventSource не умеет POST).

| event | data | Когда |
|---|---|---|
| `user_saved` | `{message_id}` | сообщение пользователя записано |
| `delta` | `{text}` | кусок текста ассистента |
| `tool_start` | `{call_id, name, args, label}` | агент вызвал инструмент; `label` — по-русски: «Читаю главу 3» |
| `tool_end` | `{call_id, name, ok, summary}` | результат (кратко, без полного payload) |
| `card` | `{call_id?, card}` | карточка UI (см. ниже) |
| `session` | `{state, allowed_events, progress}` | состояние сессии изменилось |
| `title` | `{title}` | авто-заголовок разговора (после 1-го ответа) |
| `done` | `{message_id}` | ответ завершён и сохранён |
| `error` | `{error, message}` | ошибка LLM/инструмента; поток закрывается |

При разрыве соединения генерация продолжается до конца и сохраняется; `GET /api/conversations/{uid}` вернёт итог.

## Карточки (`card`)

Хранятся в `messages.cards_json`, рендерятся фронтом специальными компонентами. Тип — поле `type`:

```jsonc
{"type": "command", "machine": "homelab", "machine_name": "Хомлаб", "command": "kubectl get pods -A",
 "explanation": [{"part": "kubectl", "text": "CLI Kubernetes"}, {"part": "get pods", "text": "список подов"}, {"part": "-A", "text": "во всех namespace"}],
 "expected": "Список подов kube-system в статусе Running", "risk": "low", "step": 2}

{"type": "question", "concept": "Service", "question": "Своими словами: зачем Service, если у пода есть IP?", "index": 1, "total": 5}

{"type": "evaluation", "verdict": "partial", "comment": "Верно про балансировку, упущено: IP пода меняется", "weak_spot": "IP пода эфемерен"}

{"type": "chapter_summary", "source": "src_…", "chapter": 3, "title": "…", "summary": "…", "key_points": ["…"]}

{"type": "block_saved", "block_uid": "blk_…", "kind": "lesson", "title": "…", "summary": "…",
 "category_suggested": "infra/kubernetes", "category_status": "suggested", "version": 1}

{"type": "block_updated", "block_uid": "blk_…", "title": "…", "from_version": 3, "to_version": 4, "reason": "…"}

{"type": "session_progress", "state": "check", "theory_done": 5, "theory_total": 5, "questions_done": 2, "questions_total": 5}

{"type": "job", "job_id": 7, "kind": "process_source", "source": "src_…", "status": "running", "progress": 3, "total": 12}
```
