# B-012 — отчёт исполнителя (2026-11-17)

## Изменённые файлы
- `server/app/modules/library/service.py` — `source_ref` отдаёт `kind` (порт для learning).
- `server/app/modules/learning/service.py` — `list_activities` добавляет `kind` в каждую активность.
- `server/app/modules/today/service.py` — `_reading`: `kind` в ответе; пропуск active-активностей
  с `cursor_chapter > total_chapters` (залипший курсор после пересборки глав).
- `web/src/app/today/page.tsx` — «Читать дальше» по kind: book → `/library/{uid}/read?ch={cursor}`,
  video/web с главами → `/library/{uid}/{cursor}`, без глав → страницу источника.
  Пустое состояние: кнопки «Открыть библиотеку» (`/library`) и «Начать разговор» (`/chat`).
- `web/src/components/chat/chat-view.tsx` — `StreamErrorBar` рендерится только при `stream.streamError`
  (регрессия 69945dd); «Повторить» сбрасывает ошибку и переотправляет.
- `web/src/components/chat/status-bars.tsx` — `StreamErrorBar`: `return null` при пустом message
  (двойная защита), цвета `rose-500` → семантический `destructive` (DESIGN.md).
- `web/src/components/courses/course-board.tsx` — «Читать» элемента курса: `?chapter=` → `?ch=`
  (ридер читает `ch`, старый параметр молча игнорировался → всегда глава 1).
- `web/src/app/library/[uid]/page.tsx` — для книг в шапке кнопка «Читать PDF» → `/read`,
  с `?ch=` от курсора активности (без входа в полноэкранный ридер раньше было не попасть).
- `web/src/lib/types.ts` — `kind` в `ActivityCard` и `TodaySnapshot.reading`.

## Тесты
- `server/tests/api/test_today.py` — +2: `reading` несёт `kind`; курсор за total не попадает в «Продолжить».
- `server/tests/api/test_mark_read.py` — +1: самозалечивание залипшего курсора (любой mark-read → done,
  курсор не откатывается). Граничный случай `cursor == total+1 → done` уже был покрыт
  (`test_mark_read_last_chapter_finishes`) — оставлен без изменений.

## Результаты проверок
- server: `ruff check` / `ruff format --check` / `lint-imports` (7 контрактов kept) / `pytest` — все зелёные.
- web: `npm run lint`, `npx tsc --noEmit`, `npm run build` — чисто.
- Preview (стенд: контейнер на tmp-каталогах + uvicorn :8765 + `next start` :3456, сиды видео+книга):
  - «Читать дальше» для видео → `/library/{uid}/2` = 200; книга → `/read?ch=2` = 200.
  - чат без ошибки стрима — плашки «Ошибка агента» в DOM нет.
  - после удаления активностей — пустое «Сегодня» с кнопками `/library` и `/chat`.

## Решения и отклонения
- Фильтр «залипших» в `_reading` оставил `total > 0 and cursor > total`: total==0 (источник без глав)
  не отфильтровывается, но ссылка для такого случая ведёт на страницу источника, не в 404.
- Плашка закрыта с двух сторон (условие в chat-view + `return null` в самом баре) — как просил план.

## Вопросы архитектору
- В course-board «Читать» элемента курса ведёт в `/read` для любых типов источника: для видео-главы
  это 404 (`/read` только для книг). В item нет kind — чинить надо портом из courses; в план B-012
  не входило, не трогал. Кандидат в B-013 (там ридер и ссылки меняются целиком).

---

# Раунд 2 — исправления ревью (2026-11-17)

1. **course-board «Читать» по kind** — элементы курса с источником несут `kind`
   (`courses/service.py::_with_progress` → `get_source`); ссылка строится общей функцией
   `web/src/lib/reading-link.ts::readingHref` (книга → `/read?ch=`, видео/статья → глава,
   без глав/типа → страница источника) — она же используется в «Сегодня», правила не дублируются.
2. **today `_reading`** — `"kind": act.get("kind") or ""` вместо дефолта `"book"`; неизвестный
   тип ведёт на страницу источника (правило в `readingHref`).
3. **rose → destructive** — не только `chat-view.tsx:310`, а все `rose-` цвета в
   `components/chat/**` (chat-start, message, cards/changes, cards/command, course-board):
   критерий «grep rose- пуст» выполняется (остались только `prose-*` типографические классы,
   это не цвет rose).
4. **Тесты** (в `tests/api/test_today.py`): видео-активность отдаёт `kind="video"` (не фейковый
   book); элементы курса несут kind источника (video и book).

Правка отчёта по замечанию раунда 1: регресс-тесты B-012 действительно ушли коммитом B-013
(311d44a, `tests/api/test_today.py`); в раунде 2 тесты задачи расширены и лежат в коммите
фикса.

Проверки: server ruff/format/lint-imports/pytest (полный прогон) — зелёные; web lint/tsc/build — чисто.
