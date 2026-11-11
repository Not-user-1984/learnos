# B-004 · Петля обучения: сделанное засчитывается (события, статусы элементов курса, повторения)

Цель: завершённая сессия, «прочитал сам» и quick-разбор закрывают нужный элемент курса и планируют
повторение. Курс — доска с явными статусами элементов. Межмодульные эффекты — через события.
Контекст: `docs/system-review-2026-11.md` §1 (требования 1–2), §3.

## Готово, когда
- [ ] Сессия по главе источника → блок с `block_sources=(source, chapter)`; элемент курса этой главы `done`.
- [ ] «Прочитал сам» → элемент курса главы `read` (засчитан как прочитанный, но не выученный).
- [ ] После `finish_session` у блока есть `review_item` с `due_at = now + 1 день`.
- [ ] У `course_items` есть статус `todo|doing|read|done`; у курса `planned|active|done` меняется сам.
- [ ] Курсы, повторения, библиотека узнают о событиях через EventBus, без прямых вызовов из learning.
- [ ] Проверки зелёные, новые тесты на каждый пункт.

## Контекст в коде
- `server/app/kernel/events.py` — `DomainEvent`, `EventBus`, публикация после коммита (`kernel/db.py:53`);
  пример подписки — `server/app/modules/search/__init__.py:31`.
- `server/app/modules/learning/service.py` — `finish` (~286), `_write_block` (~500: `activity_uid=None`,
  ветка transcript без sources), mark-read (~413), курсор (~311, ~324).
- `server/app/modules/knowledge/service.py` — `save_block(..., activity_uid=...)` (~60), `draft.sources` (~99).
- `server/app/modules/courses/service.py` — `_item_done` (~281), from-plan (~207-230); таблицы
  `courses/infra/tables.py:28`.
- `server/app/modules/review/service.py` — ленивое заведение review_items (~27, ~47), `queue` (~45).

## Изменения
1. **События** (в домене модуля-источника, `modules/<x>/events.py`, по образцу существующих `BlockSaved`):
   - learning: `SessionFinished(session_uid, block_uid, activity_uid|None, course_id|None, course_item_id|None,
     source_uid|None, chapter_idx|None)`, `ChapterRead(activity_uid, source_uid, chapter_idx, course_id|None)`.
   - courses: `CourseItemStatusChanged(course_id, item_id, status)`.
2. **learning**:
   - Сессия хранит `course_item_id` (миграция alembic, nullable). `start_session` принимает `course_item_id`;
     из него выводит activity/source/chapter.
   - `_write_block`: передавать `activity_uid` сессии; в драфт добавлять `sources=[(source_uid, chapter_idx)]`,
     если они известны (в обеих ветках — draft и transcript).
   - После успешного finish — publish `SessionFinished`; mark-read и `mark_chapter_done` — `ChapterRead`.
   - Сессия по курсу без activity — get-or-create activity по source элемента (сейчас курсор не двигается).
3. **courses**:
   - Миграция: `course_items.status` (`todo|doing|read|done`, default `todo`), `courses.status` пересчитывать.
     Бэкфилл в миграции не нужен: при первом чтении курса один раз пересчитать статусы старым `_item_done`
     и сохранить.
   - Подписки: `SessionStarted`(если нет — добавить в learning) → item `doing`; `SessionFinished` → item `done`
     (по `course_item_id`, иначе по паре source/chapter во всех курсах); `ChapterRead` → `read`, если не `done`.
   - Курс: все items `done|read` → `done`; есть `doing|done|read` → `active`.
   - `_item_done` и N+1 убрать — прогресс из колонки статуса.
   - `remove_item` перенумеровывает позиции.
4. **review**: подписка на `SessionFinished` → создать review_item для блока (`due_at=now+1d`, SM-2 дефолты),
   идемпотентно. Ленивое заведение оставить для старых блоков.
5. **REST для веба** (нужно B-005): `GET /api/review/queue?limit=`, `GET /api/review/stats`
   (`due_today`, `overdue`, `total`). `answer` остаётся через агента-экзаменатора в чате.
6. **Контракт import-linter**: learning не импортирует courses/review; связь только событиями.

## Тесты (`server/tests/`)
- finish сессии по элементу курса → item done, курс active/done, review_item создан, block_sources заполнены.
- mark-read → item read; повторный finish той же главы → done.
- review: повторное событие не дублирует item.
- миграции применяются на пустой и на копии существующей БД (`uv run python -m app.cli migrate`).

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- `cd web && npm run gen:api && npx tsc --noEmit` (если типы API поменялись)

## Риски
- Подписчик упал → публикация после коммита не откатывает finish; ловить и логировать в подписчике, не ронять.
- Две сессии по одной главе в разных курсах — закрывать во всех курсах, где есть элемент этой главы.
