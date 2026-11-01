---
id: T-048
title: "Аудит 2026-11-01, спринт 0: P0-hotfix (R-01..R-04, R-09, R-10, R-22)"
status: active
priority: high
from: внешний аудит [task_ai/reference/audit-2026-11-01.md](../reference/audit-2026-11-01.md), спринт 0
created: 2026-11-01
---

## Что нужно

Починить P0/P1-дефекты из аудита, ломающие ядро продукта («знание рождается через понимание» — всё,
что молча теряет/портит знание или создаёт иллюзию «агент всё прочитал»):

- **R-01 Обрезка tool-результатов**: `_truncate` режет строки до 4000 при окне `read_chapter`
  12000 → агент получает 1/3 главы с «уверенным» next_offset; списки >4000 симв. выбрасываются
  целиком (`{"truncated": true}`) — ломает list_blocks/list_chapters/search. Фикс: per-tool
  отключение обрезки для оконных инструментов + обрезка списков по элементам
  (`truncated_items` + hint); окно по умолчанию ≤6000; промпт quick_reviewer без «limit=24000».
- **R-02 update_block портит блок**: `_draft_from_frontmatter` теряет concepts/practice;
  «Дозакрепить» парсится построчно → пункт-мусор «[!WARNING]» и размножение callout'ов;
  `draft_to_markdown` всегда пишет `category_status: suggested` → reindex возвращает
  подтверждённые блоки во «Входящие» (и хардкод `review` затирает SRS-состояние в файле).
  Фикс: полный round-trip parse→patch→render без потерь, category_status/review из meta.
- **R-03 finish_session закрывает сессию ДО генерации блока**: сбой LLM = урок потерян
  (повторный finish запрещён can_finish). Фикс: блок сначала, закрытие потом; идемпотентный
  ретрай при «блок уже есть, сессия открыта».
- **R-04 Промпты обещают отсутствующие инструменты**: root/free_chat промпты, претрекер и
  RESEARCH_DIRECTIVE велят `add_source → process_source`, `preview_note` и пр., которых нет
  в `spec.tools` → `unknown_tool`. Фикс: выдать инструменты + тест-линтер «промпт ↔ инструменты».
- **R-09 list_blocks без tags/sources**: `_row_to_meta` всегда пустые связи → главы курса
  никогда не отмечаются пройденными (`_item_done` смотрит m.sources), карточки БЗ без источника.
  Фикс: батч-подгрузка связей в list().
- **R-10 Источник «залипает» в processing**: падение воркера/рестарт — job running навсегда,
  `_fail` не трогает sources.status, `process_source` без force отказывает. Фикс: recovery на
  старте lifespan, `_fail` обновляет источник, try/except вокруг run_job.
- **R-22 Telegram**: `proxy=""` → `ValueError` (не ловится) после первой прямой отправки;
  `chunk_for_telegram(text)[1:6]` теряет первый кусок главы; лимит считается до HTML-конвертации
  → переполнение 4096.

Верификация 2026-11-01: все семь пунктов подтверждены чтением кода (см. audit, пометка [подтв.]).

## Критерии готовности

- [ ] Тест: `read_chapter` на главе 30k через channel="agent" — по окнам агент получает весь
      текст без дыр и без обрезки
- [ ] Тест: list из 100+ элементов не превращается в `{"truncated": true}` — отдаются первые
      элементы + `truncated_items`
- [ ] Тест: save_block(concepts+practice+2 weak_spots, confirmed) → update_block(append_theses)
      → concepts/practice/weak_spots на месте, category_status в файле confirmed, reindex()
      не меняет статус; round-trip render→parse без потерь
- [ ] Тест: падение LLM в finish_session оставляет сессию активной, повторный finish создаёт блок
- [ ] Тест: root/free_chat промпты и директивы интентов не упоминают инструментов вне spec.tools
      (линтер в pytest)
- [ ] Тест: list_blocks отдаёт tags/sources; глава курса с привязанным блоком отмечается пройденной
- [ ] Тест: рестарт воркера выводит source из processing (failed с ошибкой), job не остаётся running
- [ ] Тест: прямой маршрут Telegram не падает на повторной отправке; глава читается с первого куска;
      HTML-куски ≤ 4096
- [ ] `ruff`/`lint-imports`/`pytest` зелёные, деплой на CT 132 поднялся, health ок

## Заметки

- Каждый пункт = отдельный коммит с red→green тестом.
- Промпты quick_reviewer/root: заменить «limit=24000» на «читай окнами по ~6000 (limit=6000),
  листай offset пока next_offset != null».
- R-03: `BlockWriterDraft.concepts/practice` типизировать pydantic-моделями вместо `list[dict]`.
