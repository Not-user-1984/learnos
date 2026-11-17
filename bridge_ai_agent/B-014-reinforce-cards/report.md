# B-014 — отчёт исполнителя (2026-11-17)

## Изменённые файлы

**Сервер:**
- `migrations/versions/0023_cards.py` — `blocks.cards_json` + таблица `review_card_items`
  (unique(block_uid, card_id)); то же в `knowledge/infra/tables.py` и `review/infra/tables.py`.
- `knowledge/domain.py` — `Card(id, q, a)`; `BlockDraft.cards`/`BlockMeta.cards`;
  `assign_card_ids` (устойчивые id при правках); `apply_patch` понимает `cards`;
  `draft_to_markdown` пишет карточки в frontmatter; `writer_out_to_draft` переносит карточки
  из block_writer.
- `knowledge/usecases/frontmatter.py` — карточки из frontmatter при пересборке драфта.
- `knowledge/infra/blocks_repo.py` — `cards_json` в индексе (save/update_row/_row_to_meta/_meta_dict).
- `knowledge/infra/md_store.py` — `read_meta` разбирает карточки.
- `knowledge/service.py` — `save_block`/`update_block` назначают id; `make_cards(uid)` —
  «Сделать карточки» на старом блоке.
- `knowledge/agents.py` — `CardOut` в `BlockWriterDraft` (≤5), агент `card_writer`
  (структурированный выход 3–5 карточек); промпты block_writer (правила «мякотки» + пример
  хорошей/плохой) и новый `agents/card_writer/prompt.md`.
- `knowledge/schemas.py`/`api.py` — `CardIn/CardOut`; `POST /api/kb/blocks/{uid}/cards`
  (генерация), `PATCH /api/kb/blocks/{uid}` (правка: карточки правятся/удаляются, версия
  блока сохраняется), карточки в BlockCard.
- `review/` — SM-2 на карточку: репозиторий `upsert_card/get_card/all_cards/delete`;
  `queue(limit, source)` и `stats(source)` (kind=card с q/a, kind=block — только блоки без
  карточек), `answer_card` (again=1/hard=3/good=5, без LLM), `on_session_finished` заводит
  сроки каждой карточке (due завтра); `ensure_items` мигрирует блоковый элемент на карточные.
- `review/api.py` — `?source=` в queue/stats, `POST /api/review/answer-card`;
  `review/tools.py` — `get_review_queue(source, limit)` отдаёт карточки.
- `scheduler/service.py` — digest упоминает карточки (считает через stats, туда уже входят).

**Веб:**
- `app/review/page.tsx` — карточка → «Показать ответ» → «Не помню / Трудно / Помню» (без LLM);
  блоки без карточек и «объясни своими словами» — через чат, как раньше; `?source=&title=`
  — набор по книге с чипом фильтра.
- `components/kb/block-page-client.tsx` — секция «Карточки-суть»: список, правка/удаление/
  добавление (PATCH блока), «Сделать карточки» для блоков без карточек.
- `components/library/book-digest.tsx` (новый) + `app/library/[uid]/page.tsx` — «Выжимка
  книги» по главам (саммари блоков + карточки), экспорт .md, кнопка «Закрепить книгу»
  → `/review?source=`.
- `lib/types.ts` — `BlockCardItemLike`, карточки в BlockCard, kind/card_id/q/a в ReviewQueueItem.

## Тесты
- `tests/api/test_cards_review.py` (новый, 8): генерация block_writer (3 карточки, id c1..c3),
  make_cards (версия растёт, frontmatter), правка (id сохранённых устойчив, новым — следующие),
  answer-card (good уводит из очереди, again сбрасывает интервал, неверная оценка 404),
  блок без карточек остаётся блоковым, появление карточек вытесняет блоковый элемент,
  фильтр по источнику, неизвестная карточка — 404.

## Результаты проверок
- server: ruff / format / lint-imports (7 kept) / pytest — все зелёные.
- web: lint / tsc / build — чисто.
- Preview (стенд + Chrome CDP, без скриншотов): книга → на странице «Выжимка книги» и
  «Закрепить книгу»; `/review?source=` — 3 карточки; «Показать ответ» раскрывает ответ;
  «Помню» → карточка ушла из очереди (API: c1 больше не due, осталось 2) — срок сдвинулся.
  Очередь без фильтра: 3 карточки + 1 блоковый элемент (старый блок без карточек).

## Решения и отклонения
- Карточки канонически живут в frontmatter блока (+дублируются в индекс `cards_json` для
  списков/очереди); отдельной секции в теле MD нет — страницу блока рендерит веб из индекса.
- Отдельная таблица `review_card_items` вместо колонки card_id в review_items: уникальность
  block_uid в старой таблице не позволяет несколько строк на блок, а SQLite не даёт менять
  constraint. Блоки без карточек живут как раньше в review_items.
- Оценки кнопок: «Не помню»→1, «Трудно»→3, «Помню»→5 (quality <3 = провал в SM-2).
- Удаление блока не чистит review-элементы — как и раньше (очередь пропускает через NotFound),
  поведение не менял.
- `get_review_queue` MCP остался без обязательных аргументов (source/limit опциональны).

## Вопросы архитектору
- Карточки блока не попадают в FTS-поиск (только тело блока) — при желании добавить
  `plain_text` карточек отдельной задачей.

---

# Раунд 2 — исправления ревью (2026-11-17)

1. **Типизированный PATCH** — `BlockPatchIn` (cards: list[CardIn] | None, title, summary;
   `extra="forbid"`) → мусор и короткий q дают 422, GET/PATCH после плохих данных больше не
   падают. Дубли id карточек — ValueError → 422 (`apply_patch` проверяет до сохранения).
   Тесты: невалидная карточка/неизвестное поле/дубль id → 422, версия блока не тронута;
   валидный PATCH возвращает карточки с id.
2. **patchCards проверяет res.ok** — при ошибке показывает detail (строка или список
   pydantic-ошибок), тост об успехе только после 2xx.
3. **Мягкие лимиты** — `BlockWriterDraft.cards` и `CardsOut`: 1..12 в схеме, 3–5 требует
   промпт; `writer_out_to_draft` и `generate_cards` отрезают лишнее до 5. 6 карточек от LLM →
   5 в блоке; маленький блок (1 карточка) — не фейл. Тесты на оба случая.
4. **Сироты review_card_items** — репозиторий `delete_card_items_except`; review подписан на
   `BlockUpdated` (исчезнувшие card_id чистятся, пустой набор — все) и `BlockDeleted`
   (карточные + блочный элементы). Ложный комментарий «элемент подберёт ensure_items» убран.
   Тесты: удаление карточки чистит её элемент; DELETE блока чистит оба вида.
5. **answer() на карточном блоке** — без card_id → InvalidState с подсказкой; MCP
   `answer_review` принял `card_id`: экзаменатор ставит quality, SM-2 двигает карточный
   элемент (блочный не создаётся — пинг-понг с ensure_items закрыт). Тест: отказ без card_id,
   проговор с card_id двигает срок, блочного элемента нет.
6. **Кеш блоков в очереди** — `_collect_items`: один `get_block` на блок в пределах запроса
   (stats и queue идут через общий проход).
7. **Тесты миграции** — `test_0023_cards_keeps_existing_review_items`: v1 → 0022 с данными
   в review_items → head: прогресс жив, `review_card_items` создана, `blocks.cards_json`
   есть. Форма фикстуры: ответы ≤280 символов и ≤2 предложения (тест).

Проверки: server ruff/format/lint-imports/pytest (полный прогон, +7 тестов к задаче —
итого 15 в test_cards_review.py + 1 миграционный) — зелёные; web lint/tsc/build — чисто.
Вне раунда (FTS-карточки, content:4000→весь блок) — не трогал, как и просило ревью.
