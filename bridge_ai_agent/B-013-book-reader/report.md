# B-013 — отчёт исполнителя (2026-11-17)

## Изменённые файлы

**Сервер:**
- `migrations/versions/0022_activity_position.py` — колонки `activities.position_chapter`/`position_page`
  (+ те же в `learning/infra/tables.py`, `_activity_dict`).
- `learning/domain.py` — `can_finish(..., session_kind)`: короткий путь главы (check → done,
  ≥1 ответа), машина урока не тронута.
- `learning/service.py` — `set_position` (место без прогресса); `_advance_cursor` двигает место
  за курсором; `start_session(state=…)`; `start_chapter_session`/`finish_chapter_for_conversation`
  (глава-сессия kind="chapter", block_kind="note"); `finish_session` различает kind.
- `chat/service.py` — порты `conversation_info`, `commit_chapter_conversation` (get-or-create
  разговора + сессии); `chat/usecases/stream.py` — директива агенту при активной глава-сессии
  (мини-фейнман → commit_chapter).
- `learning/tools.py` — MCP-тул `commit_chapter` (в quick_reviewer и root, REVIEW_TOOLS);
  `learning/api.py` — `POST /api/activities/{ref}/position`; `library/api.py` —
  `POST /api/sources/{ref}/chapters/{idx}/conversation/commit`.
- `today/service.py` — `_reading` отдаёт `position_chapter`/`position_page`.
- `knowledge/infra/blocks_repo.py` — **баг-фикс**: `_meta_dict` терял `verified` (get_block
  возвращал verified=False у блоков из сессий); `knowledge/usecases/generation.py` —
  `block_kind` теперь читается и из config сессии.
- `chat/agents/quick_reviewer/prompt.md` — п. 5.5: при активной сессии записи главы —
  feynman-вопросы и `commit_chapter`, preview_note не использовать.

**Веб:**
- `app/globals.css` — стили `.textLayer` (pdf.js v6, `--total-scale-factor` на холдере).
- `components/library/pdf-viewer.tsx` — text-layer поверх canvas (fail-soft: не извлёкся —
  страница остаётся картинкой); холдер `relative` + CSS-переменные масштаба.
- `components/library/pdf-reader.tsx` — место на сервере (дебаунс 1.5 c), «Глава прочитана»
  (кнопка + авто при уходе на следующую главу, один раз) → подсказка «Разобрать главу»,
  «Обсудить» (кнопка), выделение → плашка «Обсудить» → цитата в чат, `?discuss=review`.
- `components/library/pdf-study.tsx` (новый) — PdfReader + ReaderSplit (чат главы ≥1024px
  колонкой, на мобиле шторка), ключ чата = текущая глава.
- `app/library/[uid]/read/page.tsx` — единый вход: активность, место из URL > активности;
  `[chapter]?mode=pdf` → redirect `/read?ch=`; кнопка PDF у главы ведёт в `/read`.
- `components/library/source-actions.tsx` + `app/library/[uid]/page.tsx` — «Быстрый разбор»
  книги ведёт в `/read?ch=&discuss=review` (тот же чат главы).
- `components/chat/next-steps.tsx` + `chat-view.tsx` — чип «Записать в базу» для разговоров
  с context_ref: POST commit → стартовое сообщение; `types.ts` — `context_ref`, поля позиции;
  `today/page.tsx` — ссылка книги с `&page=`.

## Тесты
- `tests/api/test_chapter_commit.py` (новый, 7): позиция (хранение, следование за mark-read,
  «Сегодня»), commit-роут (get-or-create, идемпотентность), фейнман-гейт (без ответа — отказ),
  полный путь (блок verified + block_sources (источник, глава) + закрытие сессии + курсор +
  review_item), машина урока не сломана (check ≠ debrief).

## Результаты проверок
- server: ruff / format / lint-imports (7 kept) / pytest — все зелёные.
- web: lint / tsc / build — чисто.
- Preview (стенд: настоящий PDF 9 стр. с закладками и текстом, Chrome headless + CDP, без
  скриншотов — только DOM/консоль):
  - text-layer рендерится (спаны прозрачные, текст = содержимому PDF), консоль без ошибок;
  - выделение → плашка «Обсудить» → чат главы с цитатой в композере;
  - «Записать в базу» → глава-сессия (state=check) + сообщение в разговор (проверено и API);
  - повторный вход без URL → initialChapter=2/initialPage=4 из activity; `?discuss=review`
    подставляет стартовое сообщение; `mode=pdf` → 307 → `/read?ch=2`.
  - LLM на стендe выключена — агентная часть (вопросы агента) не проверялась живьём,
    покрыта тестами сервиса.

## Решения и отклонения
- Глава-сессия живёт в общей таблице sessions с `config.kind="chapter"` — отдельной таблицы
  и колонки kind не заводил (план разрешал вариант «лёгкая сессия»).
- Чип «Записать в базу» показывается и без активной сессии (клик её создаёт), и при активной
  глава-сессии в check — рядом с «Фейнман-вопросами».
- `block_kind` главы-блока = "note" (не lesson): конспект главы, не урок.
- Авто-отметка «прочитано» срабатывает только при переходе на следующую главу (не по TOC-прыжкам);
  кнопка в тулбаре отметляет текущую.
- `position_page` для повторного входа берётся только если `?ch` не задан (URL перекрывает место
  целиком, ссылкой можно делиться).

## Вопросы архитектору
- Обе критические правки вне плана (verified в `_meta_dict`, block_kind из config) — маленькие
  баг-фиксы по ходу дела, без них пункты плана не выполнялись бы. Вынести в B-012-хвосты или
  оставить здесь?
