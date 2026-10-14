# 08 — Паритет MCP: всё, что есть в вебе, есть и в MCP

## Принцип

MCP — **равноправная прослойка над ядром**, как веб-интерфейс. Всё, что пользователь может сделать в вебе, нейронка-клиент (opencode и др.) может сделать через MCP-инструменты: создать категорию, перенести блок, собрать курс, поменять настройки, подключить модель, привязать Telegram. Веб и MCP вызывают одни и те же use-case'ы сервисов; ни один из каналов не имеет собственной бизнес-логики.

Это правило действует **с этапа 1 и на каждом следующем этапе**: добавил REST-роут или кнопку в UI → добавил инструмент (или наоборот) в той же задаче.

## Как это обеспечивается технически

1. **Одно имя на операцию.** Каждый REST-роут объявляется с `operation_id`, равным имени инструмента в `ToolRegistry` (`operation_id="create_category"`). Обработчик роута и обработчик инструмента вызывают один и тот же метод сервиса с одной pydantic-моделью аргументов (роут может принимать часть аргументов из пути).
2. **Контракт-тест паритета** (`tests/contract/test_mcp_parity.py`):
   - для каждого роута под `/api` (кроме списка исключений ниже) существует инструмент с именем `operation_id`, видимый в канале `mcp`;
   - поля модели аргументов роута ⊆ поля модели аргументов инструмента;
   - каждый инструмент из каталога ниже, относящийся к уже пройденным этапам, зарегистрирован;
   - старые имена (совместимость из [04](04-api-and-mcp.md)) на месте.
   Тест красный → этап не закрыт.
3. **Исключения** (только UI или только транспорт) перечислены явно в `tests/contract/parity_exceptions.py` с причиной; добавлять туда можно только с записью в «Отчёт» этапа.

## Уровни доступа

У каждого инструмента — уровень: `read` (чтение), `write` (изменение знаний и обучения), `admin` (настройки, секреты, модели, токены, удаление). До этапа 10 (нет авторизации) доступны все уровни; с этапа 10 MCP-токен имеет уровень и область модулей (см. [этап 10](stages/10-settings-and-cloud.md) D).

MCP-аннотации инструментов заполняются из уровня: `read` → `readOnlyHint: true`; `delete_*`, `restore_*`, `rotate_*` → `destructiveHint: true`; идемпотентные `update_*`/`set_*` → `idempotentHint: true`.

## Качество инструментов для нейронки

- Описание на русском: что делает, когда вызывать, что вернёт, 1 пример аргументов, если неочевидно.
- Ответ — компактный JSON с тем, что нужно для следующего шага (id/uid, статус, `allowed_events`, ссылки), без многокилобайтных полей; длинное — по запросу отдельным инструментом (`read_chapter`, `get_block`).
- Ошибка — `{"error", "message", "hint"}`: `hint` подсказывает, как исправить («допустимые события: theory_done, ask…», «категория не найдена, похожие: …»).
- Инструменты, меняющие знания по прямой просьбе пользователя, принимают явный флаг там, где у агента и человека разные права: `set_block_category(confirm=true)` допустим, когда пользователь сам попросил «положи в ООП».

## Каталог инструментов

Колонка «Этап» — когда инструмент должен появиться. `*` — уже есть сейчас (совместимость).

### Библиотека (`library`)

| Инструмент | Уровень | Этап | Аналог в вебе |
|---|---|---|---|
| `add_source` (kind, title, url?, local_path?, course_id?) `*` | write | 1 | «Добавить источник» (YouTube/URL) |
| `upload_source_file` (filename, content_base64, title?) | write | 2 | загрузка PDF (dropzone, 📎 в чате); лимит размера как у веба |
| `list_sources` (kind?, q?, course_id?, sort?) `*` | read | 1/4 | Библиотека |
| `get_source` (source) | read | 1/4 | страница источника |
| `update_source` (source, title?, author?) | write | 4 | правка карточки источника |
| `delete_source` (source) | admin | 4 | удалить источник (нельзя, если есть блоки) |
| `process_source` (source_id, force?) `*` | write | 1/4 | «Обработать» / «Переобработать» |
| `get_job` (job_id), `list_jobs` (status?) | read | 1 | карточка job, прогресс |
| `list_chapters` `*`, `read_chapter` `*` | read | 1 | список глав, читалка |
| `research_sources` (topic, limit?) `*` | read | 1 | «Найти источники» в курсах |
| `get_source_coverage` (source), `get_chapter_coverage` (source, chapter) | read | 8F | полоски покрытия, «новое ≈ 40%» |

### Поиск (`search`)

| `search` (q, scope, limit?) | read | 1 | поиск, ⌘K |
|---|---|---|---|
| `search_chunks` (q) `*` | read | 1 | алиас |

### База знаний (`knowledge`)

| Инструмент | Уровень | Этап | Аналог в вебе |
|---|---|---|---|
| `list_blocks` (category?, tag?, kind?, source?, status?, q?, sort?, order?, limit?, offset?, course_id?) `*` | read | 1/3 | /kb с фильтрами |
| `get_block` (block_uid) `*` | read | 1 | страница блока (MD + метаданные + связи + обратные связи) |
| `save_note` (title?, draft_json?, source?, chapter?, conversation?) | write | 2 | «Сохранить» в разборе |
| `update_block` (block_uid, patch_json, reason) | write | 1 | правка через чат |
| `list_block_versions`, `get_block_version` (block_uid, version) | read | 1/3 | история версий |
| `restore_block_version` (block_uid, version) | write | 1/3 | «Откатить» |
| `list_inbox` | read | 3 | Входящие |
| `set_block_category` (block_uid, path, confirm) | write | 1/3 | «Принять» / «Выбрать другую» |
| `list_tags` | read | 3 | фильтр тегов |
| `rename_tag` (from, to) | write | 3 | (если в UI появится управление тегами — оба канала сразу) |
| `list_categories` (с счётчиками) | read | 1/3 | дерево категорий |
| `get_category` (path) | read | 3 | страница категории |
| `create_category` (path, title, color?, icon?, sort?) | write | 1/3 | Настройки → Категории, «новая категория» |
| `update_category` (path, title?, color?, icon?, sort?) | write | 3 | редактор дерева |
| `move_category` (path, new_parent_path) | write | 3 | перетаскивание в дереве |
| `delete_category` (path, move_blocks_to?) | admin | 3 | удалить узел (пустой или с переносом блоков) |
| `reindex_kb` | admin | 1 | «Переиндексировать» |
| `list_concepts` (q?, category?), `get_concept` (uid или slug) | read | 8A | /kb/concepts |
| `list_runbooks` (machine?, q?) | read | 8E | фильтр runbook |
| `add_visual` (block_uid, request), `redraw_visual` (block_uid, idx, instruction) | write | 9 | «Перерисовать», просьба в чате |
| `get_visual` (block_uid, idx, format: code\|svg_path\|png_path) | read | 9 | скачать SVG/PNG |

### Обучение (`learning`)

| Инструмент | Уровень | Этап | Аналог в вебе |
|---|---|---|---|
| `start_activity` (source, course_id?) | write | 1/4 | «Пройти по книге» |
| `list_activities` (status?), `get_activity` (activity) | read | 1/4 | сайдбар, курсор |
| `update_activity` (activity, status?: active\|paused\|done, cursor_chapter?) | write | 4 | пауза / сдвиг курсора |
| `start_session` (course_id? \| activity?, chapter?, config?) `*` | write | 1 | «Сессия» |
| `get_session_state` `*`, `list_sessions` (activity?, status?) | read | 1 | правая панель, история |
| `advance` (session_id, event, payload_json) `*` | write | 1 | ход сессии |
| `practice_step` (session_id, machine, command, explanation, expected?, risk, verify?, cleanup?) | write | 2 (verify/cleanup — 8E) | карточка команды |
| `finish_session` (session_id, block_json?) `*` | write | 1/2 | «Завершить» |
| `abandon_session` (session_id, reason?) | write | 2 | «Бросить сессию» |

### Чат (`chat`)

MCP-клиент сам является агентом, поэтому стрим ответа встроенного агента ему не нужен. Но разговоры веба доступны, чтобы продолжить их из терминала и наоборот.

| Инструмент | Уровень | Этап | Аналог в вебе |
|---|---|---|---|
| `list_conversations` (mode?, q?), `get_conversation` (uid, last_n?) | read | 2 | список разговоров, лента |
| `create_conversation` (mode, activity?, chapter?, focus_block?, title?) | write | 2 | «Новый разговор» |
| `rename_conversation`, `delete_conversation` | write | 2 | меню разговора |
| `post_message` (conversation, content) | write | 2 | отправить сообщение встроенному агенту; возвращает итоговый текст + карточки (без стрима) |

### Курсы (`courses`)

| Инструмент | Уровень | Этап | Аналог в вебе |
|---|---|---|---|
| `create_course` (title?, topic, description?, items?, plan_json?) `*` | write | 1/5 | «Новый курс» |
| `list_courses` `*`, `get_course` (с прогрессом) | read | 1/5 | /courses |
| `update_course` (course, title?, description?, category_path?, status?) | write | 5 | правка курса |
| `delete_course` (course) | admin | 5 | удалить курс |
| `add_course_item`, `remove_course_item`, `reorder_course` | write | 1/5 | элементы, ↑↓ |
| `plan_course` (topic, constraints?) → черновик | read | 5 | «Собрать агентом» |
| `create_course_from_plan` (plan_json, selected_items) | write | 5 | «Создать» из плана |
| `get_next_step` (course) | read | 5 | «Следующий шаг» |

### Повторение (`review`)

| `get_review_queue` | read | 8C | /review, бейдж |
|---|---|---|---|
| `answer_review` (item, answer) | write | 8C | ответ на вопрос |
| `send_review_now` | write | 8C | «Отправить вопрос сейчас» |
| `get_review_stats` (block?) | read | 8C | статистика повторений |

### Экспорт (`export`)

| `export_markdown` (scope, id?, max_chars?) | read | 6 | «Скопировать MD» |
|---|---|---|---|
| `export_archive` (scope, id?) → путь к ZIP и ссылка на скачивание | read | 6 | «Скачать ZIP» |

### Профиль и настройки (`profile`, `settings`)

| Инструмент | Уровень | Этап | Аналог в вебе |
|---|---|---|---|
| `get_profile` | read | 1 | Настройки → Профиль |
| `update_profile` (patch) | write | 1 | правка профиля, машин, обучения |
| `get_settings` (section) | read | 10 | любой раздел настроек |
| `update_settings` (section, values) | admin | 10 | «Сохранить» раздела (кроме секретов и пароля) |
| `list_secrets` → только метаданные | admin | 10 | статусы ключей ••••last4 |
| `set_secret` (name, value), `delete_secret` (name) | admin | 10 | «Заменить» / «Удалить» ключ; значения никогда не возвращаются |

### Модели (`llm`)

| `list_llm_providers`, `list_llm_roles` | read | 10 | Настройки → Модели |
|---|---|---|---|
| `upsert_llm_provider` (name, type, base_url, secret_name?, enabled?) | admin | 10 | добавить/изменить провайдера |
| `delete_llm_provider` (name) | admin | 10 | удалить |
| `set_llm_role` (role, provider, model, params?) | admin | 10 | роль → модель |
| `test_llm_provider` (name) → модели, `test_llm_role` (role) | admin | 1/10 | «Проверить» |

### Telegram (`telegram`)

| `get_telegram_status` | read | 10 | раздел Telegram |
|---|---|---|---|
| `telegram_bind_start` → одноразовый код | admin | 10 | «Привязать чат» |
| `telegram_send_test` | admin | 10 | «Отправить тест» |
| `send_to_telegram` (text?, block_uid?, visual?) | write | 10 | «Отправить в Telegram» (блок, визуал) |

### Скиллы (`skills`)

| `list_skills` `*` (со статусом ready/needs_config) | read | 1/10 | Настройки → Скиллы |
|---|---|---|---|
| `run_skill` (name, kwargs_json) `*` + авто-инструменты скиллов | write | 1 | — |
| `set_skill_enabled` (name, enabled) | admin | 10 | вкл/выкл скилла |

### Доступ и система

| `list_mcp_tokens` | admin | 10 | Настройки → Доступ |
|---|---|---|---|
| `create_mcp_token` (name, level, modules?) → значение один раз | admin | 10 | «Создать токен» |
| `revoke_mcp_token` (id) | admin | 10 | «Отозвать» |
| `get_health` | read | 1 | статусы сервисов |
| `list_agent_runs` (agent?, status?, limit?) | read | 1 | (статистика агентов в Настройках → Сервисы) |
| `backup_kb_now` | admin | 10 | «Сделать бэкап сейчас» |
| `get_agent_pack` → манифест, файлы, ссылка на ZIP | read | 11 | «Скачать пакет» |
| `register_agent_install`, `list_agent_installs`, `revoke_agent_install` | admin | 11 | Настройки → «Агенты и интеграции» |

## Исключения (только веб или только транспорт)

| Что | Почему нет инструмента |
|---|---|
| Вход / выход, смена пароля веба | авторизация браузера; MCP авторизуется токеном |
| SSE-стрим `POST /api/conversations/{uid}/messages` | транспорт веб-чата; для MCP есть `post_message` |
| `POST …/stop` | отмена стрима браузера |
| Бинарные ответы (`…/visuals/{idx}.svg`, `/api/export` файлом) | MCP получает путь/ссылку через `get_visual`, `export_archive` |
| Страница `/share` (PWA) | точка входа телефона; эквивалент — `add_source` |

## MCP-промпты: тот же агент, что в вебе

Чтобы opencode вёл сессию **так же**, как встроенный агент, сервер публикует MCP-prompts, собранные из тех же `prompt.md` агентов и того же `ContextBuilder` (единый источник истины — файлы промптов модулей):

| Prompt | Аргументы | Что отдаёт |
|---|---|---|
| `learnos_session` | source, chapter, config? | промпт `session_tutor` + контекст (профиль, оглавление, глава, покрытие из 8F) + порядок вызова инструментов |
| `learnos_quick_review` | source, chapter? | промпт `quick_reviewer` + контекст |
| `learnos_free` | focus_block? | промпт `free_chat` + профиль (+ блок в фокусе) |
| `learnos_review` | — | промпт `review_examiner` + очередь повторения (этап 8C) |

Появляются по мере появления агентов (этапы 2, 8). Тест: промпт MCP и системный промпт веб-агента для одинаковых входных данных совпадают.

## MCP-ресурсы

Для клиентов, умеющих прикреплять ресурсы к контексту:

| URI | Содержимое | Этап |
|---|---|---|
| `learnos://kb/categories` | дерево категорий (YAML) | 1 |
| `learnos://block/{uid}` | MD блока | 1 |
| `learnos://concept/{slug}` | MD страницы понятия | 8A |
| `learnos://source/{uid}/toc` | оглавление с summary глав | 1 |
| `learnos://profile` | профиль (машины, обучение) | 1 |
| `learnos://course/{uid}` | план курса с прогрессом (MD) | 5 |

## Эндпоинты

- `/mcp` — все инструменты, промпты и ресурсы (opencode).
- `/mcp/<module>` — только модуль (`library`, `knowledge`, `learning`, `chat`, `courses`, `review`, `export`, `settings`, `llm`, `telegram`, `skills`).
- Сейчас инструментов ~90: для клиентов, которым тяжело с длинным списком, подключай несколько узких эндпоинтов вместо общего.
