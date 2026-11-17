# B-013 · Чтение книги: один PDF-ридер с чатом главы и «Записать в базу»

Цель: книгу удобно читать в PDF и тут же разбирать главу с нейронкой; разбор заканчивается блоком в базе.
Дизайн: `docs/book-reading-flow.md` (шаги 1–4). Делать после B-012.

## Готово, когда
- [ ] Один ридер `/library/[uid]/read`: PDF + оглавление + клавиатура + справа чат главы (≥1024px), шторка на мобиле.
      `[chapter]?mode=pdf` редиректит в `/read?ch=`.
- [ ] Text-layer pdf.js: выделение текста → «Обсудить» вставляет цитату в чат главы.
- [ ] Место (глава + страница) хранится на сервере в activity; «Сегодня» и повторный вход открывают его.
- [ ] «Глава прочитана» (кнопка + при уходе на следующую главу, один раз) → mark-read и подсказка «Разобрать главу».
- [ ] Разбор без чтения: с страницы книги/главы «Разобрать с нейронкой» открывает тот же чат главы, агент ведёт по главе сам.
- [ ] В чате главы «Записать в базу»: 1–2 вопроса «перескажи своими словами» → блок `verified=true`,
      `block_sources=(source, chapter)`, событие как у сессии (курс/повторения засчитываются).
- [ ] «Быстрый разбор» (quick_reviewer) ведёт в этот же путь, отдельный сценарий не дублирует.

## Точки входа
- Ридеры: `web/src/components/library/pdf-reader.tsx`, `pdf-viewer.tsx` (canvas, `82-119`), `reader.tsx`,
  `reader-split.tsx`, `chat-panel.tsx`.
- Место: `learning` activity (+ `page` колонка, миграция); `POST /api/activities/{uid}/position` (дебаунс с клиента).
- Чат главы: `chat/service.py:~129` `chapter_conversation`; директива главы в стриме.
- Блок: `learning/service.py` `_write_block` / `finish_session` (`~271-329`, `~521-563`) — переиспользовать,
  не копировать. Вариант: разговор главы создаёт лёгкую сессию (`kind="chapter"`), «Записать» = finish с
  мини-фейнманом; стейт-машину не ломать — отдельный короткий путь `check → done`.
- Быстрый разбор: `source-actions.tsx:29-48`, `chat/scenarios.py:40-46`.

## Интерфейсы
- `POST /api/activities/{uid}/position {chapter, page}`; activity отдаёт `page`.
- `POST /api/sources/{ref}/chapters/{idx}/conversation/commit` → старт мини-фейнмана (или MCP-тул агента главы
  `commit_chapter`), итог — карточка `block_saved`.

## Проверки
- server: ruff/format/lint-imports/pytest; тесты: позиция, commit главы → verified блок + block_sources + SessionFinished.
- web: lint/tsc/build; preview: книга → выделение → цитата в чате → «Записать в базу» → блок открыт.

## Риски
- Text-layer pdf.js — CSS из пакета pdfjs-dist, версия та же, что сейчас; проверить производительность коридора рендера.
- Не открывать png. Коммит локально, без push.
