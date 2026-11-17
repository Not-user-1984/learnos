# B-012 · Баги: «Сегодня» → 404, пустое состояние, залипшая «Ошибка агента»

Цель: «Сегодня» ведёт туда, где можно продолжить; красная плашка видна только при реальной ошибке.

## Готово, когда
- [ ] «Читать дальше» не даёт 404 ни для книги, ни для видео, ни для статьи.
- [ ] Полностью прочитанные источники не висят в «Продолжить».
- [ ] Пустое «Сегодня» предлагает «Открыть библиотеку» и «Начать разговор».
- [ ] Плашка «Ошибка агента» не показывается без ошибки; «Повторить» её убирает.
- [ ] Регресс-тесты на каждый пункт; проверки зелёные.

## Точки входа и что сделать
- `web/src/components/chat/chat-view.tsx:361` + `status-bars.tsx:189` — вернуть условие
  (`streamError && …` / `return null` при пустом). Цвета `rose-500` → семантический токен destructive (`web/DESIGN.md`).
  Регрессия из 69945dd — тест компонента или e2e-проверка в preview.
- `web/src/app/today/page.tsx:86` — ссылка по `kind`: book → `/library/{uid}/read?ch={cursor}`,
  остальное → `/library/{uid}/{cursor}`. `kind` добавить в `_reading` (`server/app/modules/today/service.py:72-87`).
- `today/service.py:75` — исключать activity с `cursor_chapter > total_chapters`.
- `learning/service.py:~502` `_advance_cursor` — проверить граничный случай cursor==total+1 → done (тест).
- `today/page.tsx:92-104` — пустое состояние: ссылки `/library` и `/chat`.
- `web/src/components/courses/course-board.tsx:123` — `?chapter=` → `?ch=` (ридер читает `ch`).
- `web/src/app/library/[uid]/page.tsx` — кнопка «Читать PDF» → `/read` для книг (сейчас входа нет).

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- `cd web && npm run lint && npx tsc --noEmit && npm run build`
- Preview: «Сегодня» с видео и книгой → клик → страница открылась; чат без ошибки → плашки нет.

## Риски
- Не открывать png-скриншоты (модель текстовая). Коммит локально, без push.
